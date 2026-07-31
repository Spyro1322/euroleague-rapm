"""
scripts/sweep_alpha_holdout.py

Refits the evaluation-window RAPM across a range of regularisation strengths and
scores each on out-of-sample game-margin prediction.

WHY
Cross-validation selects the strength that minimises error INSIDE the fitting
window. That is not the same as the strength that predicts best outside it, and
the two diverge when the CV curve is flat -- which it is here: validation error
at 3,162 and at 31,620 differs in the fourth decimal place.

The held-out fit calibrates with a slope of about 1.57. Ratings are already in
points per hundred possessions, so a correctly scaled rating predicts with slope
1.0; needing to inflate by 57% means the penalty has shrunk the ratings to well
under the spread that best predicts. This sweep asks how much of the gap to the
box-score baselines that accounts for.

Two outcomes, both worth writing up:
  - prediction improves markedly at lower alpha, in which case the CV-selected
    value is too strong FOR PREDICTION and the thesis reports the distinction
    between fitting and forecasting as a finding;
  - prediction is flat in alpha, in which case regularisation is not the
    explanation and the box-score result stands on its merits.

    python3 scripts/sweep_alpha_holdout.py --alphas 100,316,1000,3162,10000
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import polars as pl

W = Path("warehouse")
R = Path("reports")


def stints(lo, hi):
    return pl.read_parquet(W / "stints_ids.parquet").filter(
        (pl.col("Season") >= lo) & (pl.col("Season") <= hi) & (pl.col("poss") > 0))


def game_x(st, ratings):
    """Possession-weighted rating differential per game, in points, plus the
    share of player-slots that carried a rating."""
    home = st["home_players"].to_list()
    away = st["away_players"].to_list()
    poss = st["poss"].to_numpy()
    x = np.zeros(len(home)); seen = miss = 0
    for i, (h, a) in enumerate(zip(home, away)):
        t = 0.0
        for p in h:
            v = ratings.get(p)
            if v is None: miss += 1
            else: seen += 1; t += v
        for p in a:
            v = ratings.get(p)
            if v is None: miss += 1
            else: seen += 1; t -= v
        x[i] = t
    df = pl.DataFrame({"Season": st["Season"].to_numpy(),
                       "Gamecode": st["Gamecode"].to_numpy(),
                       "x": x * poss / 100.0,
                       "y": st["margin"].to_numpy().astype(float)})
    g = df.group_by(["Season", "Gamecode"]).agg(
        [pl.col("x").sum().alias("x"), pl.col("y").sum().alias("y")])
    return g, seen / max(seen + miss, 1)


def evaluate(tr, te, ratings):
    gtr, _ = game_x(tr, ratings)
    gte, cov = game_x(te, ratings)
    xtr, ytr = gtr["x"].to_numpy(), gtr["y"].to_numpy()
    xte, yte = gte["x"].to_numpy(), gte["y"].to_numpy()
    a, b = np.linalg.lstsq(np.column_stack([np.ones_like(xtr), xtr]), ytr,
                           rcond=None)[0]
    yhat = a + b * xte
    resid = yte - yhat
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    r0 = float(np.sqrt(np.mean((yte - ytr.mean()) ** 2)))
    corr = float(np.corrcoef(yhat, yte)[0, 1])
    hit = float(np.mean(np.sign(yhat) == np.sign(yte)))
    return dict(rmse=rmse, improvement=100 * (r0 - rmse) / r0, corr=corr,
                hit=hit, slope=float(b), coverage=cov, naive_rmse=r0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alphas", default="100,316,1000,3162,10000,31620")
    ap.add_argument("--prefix", default="rapm_eval")
    ap.add_argument("--train", default="2020-2024")
    ap.add_argument("--test", default="2025")
    ap.add_argument("--skip-fit", action="store_true",
                    help="reuse existing sweep_a<alpha> outputs")
    a = ap.parse_args()

    tl, th = (int(v) for v in a.train.split("-"))
    el = eh = int(a.test)
    tr, te = stints(tl, th), stints(el, eh)
    print(f"train games from {tr.height:,} stints; hold-out from {te.height:,}")

    rows = []
    for alpha in [float(x) for x in a.alphas.split(",")]:
        stem = f"sweep_a{int(alpha)}"
        if not a.skip_fit:
            cmd = [sys.executable, "scripts/fit_ridge_rapm.py",
                   "--prefix", a.prefix, "--alpha", str(alpha),
                   "--min-poss", "0", "--min-games", "0",
                   "--bootstrap", "0", "--out", stem]
            print(f"\nfitting alpha={alpha:g} ...")
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                print(p.stdout[-1500:]); print(p.stderr[-1500:])
                raise SystemExit(f"fit failed at alpha={alpha}")
        d = pl.read_parquet(W / f"{stem}.parquet")
        ratings = dict(zip(d["player_id"].to_list(), d["RAPM"].to_list()))
        m = evaluate(tr, te, ratings)
        m.update(alpha=alpha, players=d.height, rapm_sd=float(d["RAPM"].std()))
        rows.append(m)
        print(f"  alpha={alpha:>8g}  players={d.height:>4}  "
              f"sd(RAPM)={m['rapm_sd']:.3f}  RMSE={m['rmse']:.3f}  "
              f"corr={m['corr']:+.3f}  slope={m['slope']:.3f}")

    res = pl.DataFrame(rows).sort("rmse")
    print("\n" + "=" * 74)
    print("OUT-OF-SAMPLE GAME PREDICTION BY REGULARISATION STRENGTH")
    print("=" * 74)
    print(res.select(["alpha", "rapm_sd", "rmse", "improvement", "corr", "hit",
                      "slope", "players"]))

    best = res.row(0, named=True)
    print(f"\nbest out-of-sample alpha: {best['alpha']:g} "
          f"(RMSE {best['rmse']:.3f}, slope {best['slope']:.3f})")
    print("  Compare against the cross-validated value used in Chapter 4.")
    print("  A best-predicting alpha well below the CV-selected one means the")
    print("  penalty is tuned for fit rather than forecast \u2014 report the")
    print("  distinction rather than silently adopting the better number, and")
    print("  keep the CV value for the published ratings unless there is a")
    print("  principled reason to prefer predictive calibration.")
    near1 = res.filter((pl.col("slope") - 1.0).abs() < 0.25)
    if near1.height:
        print(f"\n  alpha values whose slope is near 1.0 (well-calibrated): "
              f"{near1['alpha'].to_list()}")

    R.mkdir(exist_ok=True)
    (R / "sweep_alpha_holdout.json").write_text(
        json.dumps(res.to_dicts(), indent=2, default=float))
    print("\nwrote reports/sweep_alpha_holdout.json")


if __name__ == "__main__":
    main()
