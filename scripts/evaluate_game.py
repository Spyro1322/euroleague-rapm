"""
scripts/evaluate_game.py

Held-out evaluation at TEAM-GAME level. This is the primary test; the
stint-level test in evaluate_holdout.py is reported alongside it as a null, for
a reason worth stating up front.

WHY GAME LEVEL IS THE PRIMARY TEST
The hold-out season contains roughly 14,000 stints across 402 games -- about 35
stints per game, so a median stint of about four possessions. At four
possessions the outcome is two or three shots, and the target (margin per 100
possessions) moves by 50 or 75 points on a single make. Its standard deviation
is around 126. The signal being predicted -- ten players' ratings summed, each a
few points per 100 -- spans perhaps 15. Signal-to-noise near 0.1 caps the
attainable R-squared around 0.01 no matter how good the ratings are.

Every rating in the comparison therefore lands within a fraction of a percent of
every other, and the ordering at that level is noise. That is a property of
Euroleague substitution patterns, not of the ratings, and it is a legitimate
methodological finding: it says the stint is the wrong unit at which to compare
season-level player ratings, and it pre-empts the question of why the obvious
test was not used.

Aggregating to the game averages roughly 140 possessions of that noise while the
rating signal accumulates, which is where the arms become distinguishable. It is
also the level a practitioner cares about.

TESTS
  1. game margin       predicted vs actual, RMSE / correlation / winner hit rate
  2. common support    the same, restricted to games in which every arm has a
                       rating for every player, so no arm is advantaged by
                       having its gaps filled with the league mean
  3. calibration       actual margin by predicted decile

    python3 scripts/evaluate_game.py
"""

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

W = Path("warehouse")
R = Path("reports")
BUCKETS = ["at_rim", "mid_range", "corner_three", "above_break_three"]


def load_boxscore_arm(col, lo, hi):
    m = pl.read_parquet(W / "eval_boxscore_metrics.parquet").filter(
        (pl.col("Season") >= lo) & (pl.col("Season") <= hi))
    a = (m.group_by("Player_ID")
           .agg((pl.col(col) * pl.col("minutes")).sum().alias("n"),
                pl.col("minutes").sum().alias("d"))
           .with_columns((pl.col("n") / pl.col("d")).alias("v")))
    return dict(zip(a["Player_ID"].to_list(), a["v"].to_list()))


def load_rapm_arm(stem):
    d = pl.read_parquet(W / f"{stem}.parquet")
    return dict(zip(d["player_id"].to_list(), d["RAPM"].to_list()))


def load_shotctx_arm(window):
    p = W / f"shotctx_{window}.parquet"
    if not p.exists():
        return {}
    d = pl.read_parquet(p).with_columns(
        pl.when(pl.col("verdict") == "NONE").then(pl.col("prior"))
          .otherwise(pl.col("value")).alias("eff"))
    share = {}
    for b in BUCKETS:
        f = W / f"shotctx_{window}_{b}_design.npz"
        if f.exists():
            share[b] = float(np.load(f, allow_pickle=True)["w"].sum())
    tot = sum(share.values()) or 1.0
    share = {k: v / tot for k, v in share.items()}
    d = d.with_columns(pl.col("bucket").replace_strict(
        share, default=0.0, return_dtype=pl.Float64).alias("s"))
    c = (d.with_columns((pl.col("eff") * pl.col("s")).alias("c"))
           .group_by("player_id").agg(pl.col("c").sum().alias("v")))
    return dict(zip(c["player_id"].to_list(), c["v"].to_list()))


def stints(lo, hi):
    return pl.read_parquet(W / "stints_ids.parquet").filter(
        (pl.col("Season") >= lo) & (pl.col("Season") <= hi) & (pl.col("poss") > 0))


def game_table(st, arms):
    """
    Per game: the possession-weighted rating differential for each arm, expressed
    in points, plus the actual margin and a per-arm completeness flag.

    A stint's differential is (sum of home ratings - sum of away ratings); scaling
    by that stint's possessions and summing over the game gives the points the
    ratings imply, which is directly comparable to the observed margin.
    """
    home = st["home_players"].to_list()
    away = st["away_players"].to_list()
    poss = st["poss"].to_numpy()
    season = st["Season"].to_numpy()
    game = st["Gamecode"].to_numpy()

    cols = {}
    coverage = {}
    for name, rat in arms.items():
        x = np.zeros(len(home))
        cov = np.zeros(len(home))
        for i, (h, a) in enumerate(zip(home, away)):
            tot = 0.0; seen = 0
            for p in h:
                v = rat.get(p)
                if v is not None:
                    seen += 1; tot += v
            for p in a:
                v = rat.get(p)
                if v is not None:
                    seen += 1; tot -= v
            x[i] = tot
            cov[i] = seen / 10.0
        cols[name] = x * poss / 100.0
        coverage[name] = cov

    df = pl.DataFrame({
        "Season": season, "Gamecode": game, "poss": poss,
        "margin": st["margin"].to_numpy().astype(float),
        **{f"x_{k}": v for k, v in cols.items()},
        **{f"cov_{k}": v for k, v in coverage.items()},
    })
    agg = df.group_by(["Season", "Gamecode"]).agg(
        [pl.col("poss").sum().alias("poss"), pl.col("margin").sum().alias("y")]
        + [pl.col(f"x_{k}").sum().alias(f"x_{k}") for k in arms]
        # Coverage is a possession-weighted SHARE of rated player-slots, not an
        # all-or-nothing flag. Requiring every player in every stint of a game to
        # be rated disqualifies a game for a single unrated debutant: with ten
        # players across ~35 stints that criterion retained 2 games of 402 and
        # measured nothing.
        + [((pl.col(f"cov_{k}") * pl.col("poss")).sum()
            / pl.col("poss").sum()).alias(f"cov_{k}") for k in arms]
    )
    return agg


def wls(x, y):
    X = np.column_stack([np.ones_like(x), x])
    return np.linalg.lstsq(X, y, rcond=None)[0]


def score(y, yhat):
    resid = y - yhat
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    corr = float(np.corrcoef(yhat, y)[0, 1]) if np.std(yhat) > 0 else float("nan")
    hit = float(np.mean(np.sign(yhat) == np.sign(y)))
    ss = float(np.sum(resid ** 2)); st_ = float(np.sum((y - y.mean()) ** 2))
    return rmse, corr, hit, 1 - ss / st_ if st_ else float("nan")


def run(tr_g, te_g, arms, label, mask_col=None):
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    tr = tr_g; te = te_g
    if mask_col is not None:
        thr = mask_col
        tr = tr.filter(pl.Series(np.logical_and.reduce(
            [tr[f"cov_{k}"].to_numpy() >= thr for k in arms])))
        te = te.filter(pl.Series(np.logical_and.reduce(
            [te[f"cov_{k}"].to_numpy() >= thr for k in arms])))
    print(f"games: {tr.height:,} train, {te.height:,} hold-out")
    if te.height < 30:
        print("  too few games to evaluate."); return []

    y_tr = tr["y"].to_numpy(); y_te = te["y"].to_numpy()
    base = float(y_tr.mean())
    r0, _, h0, _ = score(y_te, np.full_like(y_te, base))
    print(f"\nnaive (home advantage {base:+.2f} pts): RMSE {r0:.3f}  "
          f"winner {h0:.1%}")

    out = [dict(arm="naive", rmse=r0, corr=float("nan"), hit=h0, r2=0.0,
                improvement=0.0, slope=None)]
    for name in arms:
        xtr = tr[f"x_{name}"].to_numpy(); xte = te[f"x_{name}"].to_numpy()
        a, b = wls(xtr, y_tr)
        yhat = a + b * xte
        rmse, corr, hit, r2 = score(y_te, yhat)
        imp = 100 * (r0 - rmse) / r0
        print(f"\n[{name}]  intercept {a:+.2f}  slope {b:+.3f}")
        print(f"  RMSE {rmse:.3f} ({imp:+.2f}% vs naive)   corr {corr:+.3f}   "
              f"winner {hit:.1%}   R2 {r2:+.4f}")
        if abs(b - 1.0) > 0.3:
            print(f"  note: slope {b:.2f} rather than 1.0 \u2014 the ratings are "
                  f"{'under' if b > 1 else 'over'}-dispersed relative to what best "
                  f"predicts out of sample, i.e. the regularisation is "
                  f"{'too strong' if b > 1 else 'too weak'} for prediction.")
        out.append(dict(arm=name, rmse=rmse, corr=corr, hit=hit, r2=r2,
                        improvement=imp, slope=float(b)))

    res = pl.DataFrame(out).sort("rmse")
    print()
    print(res.select(["arm", "rmse", "improvement", "corr", "hit", "r2", "slope"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2020-2024")
    ap.add_argument("--test", default="2025")
    ap.add_argument("--rapm-stem", default="rapm_eval")
    ap.add_argument("--shotctx-window", default="eval")
    a = ap.parse_args()

    tl, th = (int(v) for v in a.train.split("-"))
    el = eh = int(a.test) if "-" not in a.test else None
    if el is None:
        el, eh = (int(v) for v in a.test.split("-"))

    print(f"train {tl}-{th}   hold-out {el}-{eh}")
    arms = {}
    arms["pir"] = load_boxscore_arm("pir_per40_z", tl, th)
    arms["win_score"] = load_boxscore_arm("ws_per40_z", tl, th)
    arms["rapm"] = load_rapm_arm(a.rapm_stem)
    sc = load_shotctx_arm(a.shotctx_window)
    if sc:
        arms["shotctx"] = sc
    for k, v in arms.items():
        print(f"  {k}: {len(v):,} rated players")

    tr_g = game_table(stints(tl, th), arms)
    te_g = game_table(stints(el, eh), arms)

    print("\nper-arm mean share of hold-out player-slots carrying a rating:")
    for k in arms:
        print(f"  {k:10} {te_g[f'cov_{k}'].mean():.3f}")

    full = run(tr_g, te_g, arms, "TEST 1 \u2014 ALL HOLD-OUT GAMES "
                                 "(unrated players treated as league-average)")
    comm = run(tr_g, te_g, arms, "TEST 2 \u2014 COMMON SUPPORT "
                                 "(games where every arm rates >= 85% of slots)",
               mask_col=0.85)

    R.mkdir(exist_ok=True)
    (R / "eval_game.json").write_text(json.dumps(
        dict(train=a.train, test=a.test, full=full, common_support=comm),
        indent=2, default=float))
    print("\nwrote reports/eval_game.json")

    print("\nNOTE ON COVERAGE")
    print("  The RAPM arm is limited to the players in its published leaderboard,")
    print("  which applies a possession floor. The floor exists for display, not")
    print("  for evaluation, and it caps this arm's coverage below the box-score")
    print("  arms'. To remove the handicap, refit with the floors disabled and")
    print("  point --rapm-stem at that output:")
    print("    python3 scripts/fit_ridge_rapm.py --prefix rapm_eval --alpha <a> \\")
    print("        --min-poss 0 --min-games 0 --bootstrap 0 --out rapm_eval_full")


if __name__ == "__main__":
    main()