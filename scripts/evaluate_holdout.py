"""
scripts/evaluate_holdout.py

Held-out evaluation (O-eval). Ratings estimated on the training window are used
to predict outcomes in a season none of them has seen.

DESIGN
  target      point differential per 100 possessions, per stint
  weight      possessions (a two-possession stint should not count as much as a
              twenty-possession one)
  train       2020-2024  -- the window rapm_eval was fitted on
  hold-out    2025       -- never seen by any rating in the comparison
  scaling     ONE coefficient pair (intercept, slope) per arm, fitted on the
              TRAINING stints and applied FROZEN to the hold-out.

Why frozen. Fitting the scaling inside the hold-out measures how well a rating
CORRELATES with outcomes it has already seen, which is a weaker claim than
prediction and is what a good deal of published comparison actually does. Frozen
coefficients ask the harder question: given only what was knowable before the
season, how close does each rating come? Both are reported, so the gap between
them is visible rather than hidden.

ARMS
  naive        predict the training mean. The floor any rating must beat.
  pir          the competition's official efficiency rating, per 40 min, z-scored
  win_score    Berri's Win Score, same treatment
  rapm         classical RAPM from Chapter 4
  shotctx      the shot-context composite from Chapter 5

A NOTE ON WHAT THE SHOT-CONTEXT ARM CAN SHOW HERE
This test predicts OVERALL margin, and the shot-context model is not designed to
improve overall prediction -- its contexts are shrunk toward the overall rating,
so a composite of them approximates that rating by construction. Parity with
classical RAPM is the expected result and is not a failure. The claim of
Chapter 5 is that the contexts carry DIFFERENT information, not more of the same,
and the test of that is context-specific prediction (evaluate_context.py), not
this one. Reporting the parity result honestly here is what makes the
context-specific result credible when it follows.

    python3 scripts/evaluate_holdout.py
"""

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

W = Path("warehouse")
R = Path("reports")
BUCKETS = ["at_rim", "mid_range", "corner_three", "above_break_three"]


# ----------------------------------------------------------------- ratings
def load_boxscore_arm(col: str, lo: int, hi: int) -> dict:
    """Player -> z-scored rate, averaged over the training seasons."""
    m = pl.read_parquet(W / "eval_boxscore_metrics.parquet").filter(
        (pl.col("Season") >= lo) & (pl.col("Season") <= hi))
    agg = (m.group_by("Player_ID")
             .agg((pl.col(col) * pl.col("minutes")).sum().alias("num"),
                  pl.col("minutes").sum().alias("den"))
             .with_columns((pl.col("num") / pl.col("den")).alias("v")))
    return dict(zip(agg["Player_ID"].to_list(), agg["v"].to_list()))


def load_rapm_arm(stem: str) -> dict:
    d = pl.read_parquet(W / f"{stem}.parquet")
    # verify the additive convention before relying on it
    if {"ORAPM", "DRAPM", "RAPM"}.issubset(d.columns):
        err = float((d["ORAPM"] + d["DRAPM"] - d["RAPM"]).abs().max())
        print(f"    convention check: max |ORAPM + DRAPM - RAPM| = {err:.4f}")
        if err > 0.01:
            print("    !! RAPM is not the sum of its parts. The margin construction")
            print("       below assumes it is; check Chapter 4 before trusting this arm.")
    return dict(zip(d["player_id"].to_list(), d["RAPM"].to_list()))


def load_shotctx_arm(window: str) -> dict:
    """
    Composite = sum over contexts of (league share of that context) x (that
    player's context rating), offence and defence combined.

    Contexts with no measurable signal are taken at their prior rather than their
    fitted value: the fitted value there is noise, and including it would import
    that noise into a prediction. The composite therefore degrades gracefully --
    if nothing were identified it would reduce exactly to the overall rating.
    """
    p = W / f"shotctx_{window}.parquet"
    if not p.exists():
        return {}
    d = pl.read_parquet(p)
    d = d.with_columns(
        pl.when(pl.col("verdict") == "NONE").then(pl.col("prior"))
          .otherwise(pl.col("value")).alias("eff"))

    # league share of each context, from the design supports
    share = {}
    for b in BUCKETS:
        f = W / f"shotctx_{window}_{b}_design.npz"
        if f.exists():
            share[b] = float(np.load(f, allow_pickle=True)["w"].sum())
    tot = sum(share.values()) or 1.0
    share = {k: v / tot for k, v in share.items()}
    print(f"    context shares: " + ", ".join(f"{k}={v:.3f}" for k, v in share.items()))

    d = d.with_columns(
        pl.col("bucket").replace_strict(share, default=0.0,
                                        return_dtype=pl.Float64).alias("share"))
    # defence is stored positive-for-good, so both ends add
    comp = (d.with_columns((pl.col("eff") * pl.col("share")).alias("c"))
              .group_by("player_id").agg(pl.col("c").sum().alias("v")))
    return dict(zip(comp["player_id"].to_list(), comp["v"].to_list()))


# ----------------------------------------------------------------- stints
def stint_frame(lo: int, hi: int) -> pl.DataFrame:
    s = pl.read_parquet(W / "stints_ids.parquet").filter(
        (pl.col("Season") >= lo) & (pl.col("Season") <= hi) & (pl.col("poss") > 0))
    return s.with_columns((100.0 * pl.col("margin") / pl.col("poss")).alias("y"))


def build_x(st: pl.DataFrame, ratings: dict) -> tuple[np.ndarray, float]:
    """Home rating sum minus away rating sum. Unrated players contribute 0
    (the league mean), and the coverage rate is returned so a thin arm is visible."""
    home = st["home_players"].to_list()
    away = st["away_players"].to_list()
    x = np.zeros(len(home))
    seen = miss = 0
    for i, (h, a) in enumerate(zip(home, away)):
        tot = 0.0
        for p in h:
            v = ratings.get(p)
            if v is None:
                miss += 1
            else:
                seen += 1; tot += v
        for p in a:
            v = ratings.get(p)
            if v is None:
                miss += 1
            else:
                seen += 1; tot -= v
        x[i] = tot
    return x, seen / max(seen + miss, 1)


def wstats(y, yhat, w):
    resid = y - yhat
    rmse = float(np.sqrt(np.average(resid ** 2, weights=w)))
    mae = float(np.average(np.abs(resid), weights=w))
    ybar = float(np.average(y, weights=w))
    ss_res = float(np.sum(w * resid ** 2))
    ss_tot = float(np.sum(w * (y - ybar) ** 2))
    return rmse, mae, 1.0 - ss_res / ss_tot if ss_tot else float("nan")


def wls(x, y, w, arm=""):
    """
    Weighted least squares for y = a + b x.

    A constant predictor makes the normal equations singular. In practice that
    means every player lookup missed -- an identifier-space mismatch between the
    ratings and the lineups -- which is a data-join bug, not a numerical one, and
    is worth saying so rather than surfacing a LinAlgError.
    """
    if np.allclose(x, x[0] if len(x) else 0.0):
        raise SystemExit(
            f"\n  FATAL [{arm}]: the predictor is constant ({float(x[0]) if len(x) else 0.0:.3f}).\n"
            f"  Every player lookup missed, so the rating and the lineups are on\n"
            f"  different identifier spaces. Compare a sample of ids from\n"
            f"  stints_ids.home_players against the rating table's key column --\n"
            f"  whitespace and prefix differences are the usual cause.")
    X = np.column_stack([np.ones_like(x), x])
    WX = X * w[:, None]
    beta = np.linalg.solve(X.T @ WX, WX.T @ y)
    return float(beta[0]), float(beta[1])


def calibration(y, yhat, w, n_bins=10):
    order = np.argsort(yhat)
    bins = np.array_split(order, n_bins)
    rows = []
    for i, b in enumerate(bins, 1):
        rows.append(dict(decile=i,
                         pred=float(np.average(yhat[b], weights=w[b])),
                         actual=float(np.average(y[b], weights=w[b])),
                         poss=float(w[b].sum())))
    return pl.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2020-2024")
    ap.add_argument("--test", default="2025")
    ap.add_argument("--rapm-stem", default="rapm_eval")
    ap.add_argument("--shotctx-window", default="eval")
    args = ap.parse_args()

    tr_lo, tr_hi = (int(v) for v in args.train.split("-"))
    te_lo, te_hi = (int(v) for v in (args.test.split("-") if "-" in args.test
                                     else (args.test, args.test)))

    print(f"train {tr_lo}-{tr_hi}   hold-out {te_lo}-{te_hi}")
    tr = stint_frame(tr_lo, tr_hi)
    te = stint_frame(te_lo, te_hi)
    print(f"stints: {tr.height:,} train, {te.height:,} hold-out")
    if te.is_empty():
        raise SystemExit("no hold-out stints — check the season range.")

    ytr, wtr = tr["y"].to_numpy(), tr["poss"].to_numpy()
    yte, wte = te["y"].to_numpy(), te["poss"].to_numpy()

    print("\nloading arms:")
    arms = {}
    print("  pir");        arms["pir"] = load_boxscore_arm("pir_per40_z", tr_lo, tr_hi)
    print("  win_score");  arms["win_score"] = load_boxscore_arm("ws_per40_z", tr_lo, tr_hi)
    print("  rapm");       arms["rapm"] = load_rapm_arm(args.rapm_stem)
    print("  shotctx");    arms["shotctx"] = load_shotctx_arm(args.shotctx_window)
    arms = {k: v for k, v in arms.items() if v}

    # ---- naive floor
    a0 = float(np.average(ytr, weights=wtr))
    rmse0, mae0, r20 = wstats(yte, np.full_like(yte, a0), wte)
    print(f"\nnaive (training mean {a0:+.2f}):  RMSE {rmse0:.3f}   MAE {mae0:.3f}")

    results = [dict(arm="naive", rmse=rmse0, mae=mae0, r2=0.0,
                    improvement=0.0, slope=None, coverage=1.0)]
    cals = {}

    for name, rat in arms.items():
        xtr, cov_tr = build_x(tr, rat)
        xte, cov_te = build_x(te, rat)
        if cov_tr < 0.01:
            raise SystemExit(
                f"\n  FATAL [{name}]: {cov_tr:.1%} player coverage on the training\n"
                f"  stints. The rating table and the lineups use different\n"
                f"  identifier spaces. Fix the join before evaluating.")
        a, b = wls(xtr, ytr, wtr, arm=name)          # frozen on training
        yhat = a + b * xte
        rmse, mae, r2 = wstats(yte, yhat, wte)
        imp = 100.0 * (rmse0 - rmse) / rmse0

        # The rate target is heavy-tailed: a one-possession stint decided by a
        # three yields +/-300 points per 100. Weighting by possessions is the
        # correct estimator but leaves those rows dominating a reported RMSE, so
        # the same predictions are also scored on raw stint margin, which is
        # bounded by the stint length and is the scale a reader can interpret.
        pts_hat = yhat * wte / 100.0
        pts_act = te["margin"].to_numpy().astype(float)
        rmse_pts = float(np.sqrt(np.mean((pts_act - pts_hat) ** 2)))
        rmse_pts0 = float(np.sqrt(np.mean((pts_act - a0 * wte / 100.0) ** 2)))
        imp_pts = 100.0 * (rmse_pts0 - rmse_pts) / rmse_pts0

        # what the same arm would score if allowed to refit on the hold-out
        a2, b2 = wls(xte, yte, wte)
        rmse_in, _, _ = wstats(yte, a2 + b2 * xte, wte)

        print(f"\n[{name}]")
        print(f"  player coverage: train {cov_tr:.3f}  hold-out {cov_te:.3f}")
        print(f"  frozen scaling: intercept {a:+.3f}, slope {b:+.4f}")
        print(f"  rate scale : RMSE {rmse:.3f}  MAE {mae:.3f}  R2 {r2:+.4f}  "
              f"vs naive {imp:+.2f}%")
        print(f"  margin scale: RMSE {rmse_pts:.3f} points/stint  "
              f"vs naive {imp_pts:+.2f}%")
        print(f"  (refit on hold-out would give RMSE {rmse_in:.3f} \u2014 the gap is "
              f"the cost of honest prediction)")
        if cov_te < 0.9:
            print(f"  !! only {cov_te:.1%} of hold-out player-slots have a rating; "
                  f"unrated players are treated as league-average, which flatters "
                  f"this arm by shrinking its predictions toward the mean.")
        if b < 0:
            print("  !! NEGATIVE SLOPE — this rating predicts outcomes in the wrong "
                  "direction out of sample. Do not report without explanation.")

        results.append(dict(arm=name, rmse=rmse, mae=mae, r2=r2, improvement=imp,
                            rmse_pts=rmse_pts, improvement_pts=imp_pts,
                            slope=b, coverage=cov_te, rmse_refit=rmse_in))
        cals[name] = calibration(yte, yhat, wte)

    res = pl.DataFrame(results).sort("rmse")
    print("\n" + "=" * 66)
    print("STINT DIFFERENTIAL, HOLD-OUT (lower RMSE is better)")
    print("=" * 66)
    cols = [c for c in ("arm", "rmse", "improvement", "rmse_pts",
                        "improvement_pts", "r2", "coverage") if c in res.columns]
    print(res.select(cols))

    # ---- secondary: team-game margin
    print("\n" + "=" * 66)
    print("SECONDARY: TEAM-GAME MARGIN")
    print("=" * 66)
    best = res.filter(pl.col("arm") != "naive")["arm"][0]
    print(f"  aggregating stint predictions to game level for the leading arm ({best})")
    rat = arms[best]
    xte, _ = build_x(te, rat)
    a, b = wls(build_x(tr, rat)[0], ytr, wtr, arm=best)
    te2 = te.with_columns([
        pl.Series("pred_pts", (a + b * xte) * te["poss"].to_numpy() / 100.0),
        pl.Series("act_pts", te["margin"].to_numpy().astype(float)),
    ])
    g = te2.group_by(["Season", "Gamecode"]).agg([
        pl.col("pred_pts").sum().alias("pred"),
        pl.col("act_pts").sum().alias("actual")])
    gr = float(np.corrcoef(g["pred"].to_numpy(), g["actual"].to_numpy())[0, 1])
    hit = float(np.mean(np.sign(g["pred"].to_numpy()) == np.sign(g["actual"].to_numpy())))
    print(f"  games: {g.height:,}")
    print(f"  corr(predicted, actual game margin) = {gr:+.3f}")
    print(f"  winner correctly identified in {hit:.1%} of games")
    print("  (a coin flip is 50%; home advantage alone typically reaches ~60%)")

    # ---- calibration for the leading arm
    print(f"\ncalibration by predicted decile ({best}):")
    print(cals[best])
    print("  A well-calibrated rating has actual tracking predicted down the column.")
    print("  Systematic flattening means the ratings are over-dispersed.")

    R.mkdir(exist_ok=True)
    out = dict(train=args.train, test=args.test, naive_rmse=rmse0,
               results=res.to_dicts(), game_corr=gr, game_hit_rate=hit)
    (R / "eval_holdout.json").write_text(json.dumps(out, indent=2, default=float))
    res.write_parquet(W / "eval_holdout_results.parquet")
    print("\nwrote reports/eval_holdout.json and warehouse/eval_holdout_results.parquet")


if __name__ == "__main__":
    main()