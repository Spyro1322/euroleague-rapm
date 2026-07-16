#!/usr/bin/env python3
"""
scripts/fit_ridge_rapm.py  —  Week 3, action 2b + leaderboard export.

Fits weighted ridge on the offense/defense design matrix, selects lambda by
game-grouped CV, splits O/D, computes possession-block-bootstrap credible
intervals, and exports a baseline leaderboard.

    (X'WX + λI) β = X'W y     via sklearn Ridge(solver="lsqr"|"sparse_cg")

Outputs:
    warehouse/rapm_baseline.parquet   player_id, name, poss, ORAPM, DRAPM,
                                      RAPM, RAPM_lo, RAPM_hi
    warehouse/rapm_baseline.csv       same, human-readable

Run after build_rapm_design.py. Sign conventions match build_rapm_design.py:
ORAPM = off coef, DRAPM = -def coef, positive = good on both ends.
"""
from __future__ import annotations
import argparse
import logging

import numpy as np
import polars as pl
import scipy.sparse as sp
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

LOG = logging.getLogger("rapm_fit")

# defaults; overridden by --prefix
DESIGN_NPZ = "warehouse/rapm_design.npz"
DESIGN_X = "warehouse/rapm_design.X.npz"
PLAYERS = "warehouse/rapm_players.parquet"
ID_MAP = "warehouse/player_id_map.parquet"      # for names on the leaderboard
OUT_PARQUET = "warehouse/rapm_baseline.parquet"
OUT_CSV = "warehouse/rapm_baseline.csv"

# λ grid. RAPM optima sit high because of lineup collinearity — start broad.
ALPHAS = np.logspace(1.5, 4.5, 16)
SOLVER = "lsqr"          # good for large sparse; "sparse_cg" is an alternative
MIN_POSS = 500          # leaderboard filter: min total possessions on court


def load(prefix="rapm"):
    d = np.load(f"warehouse/{prefix}_design.npz", allow_pickle=True)
    X = sp.load_npz(f"warehouse/{prefix}_design.X.npz").tocsr()
    return X, d["y"].astype(float), d["w"].astype(float), d["groups"]


def wmse(y, yhat, w) -> float:
    return float(np.average((y - yhat) ** 2, weights=w))


def select_alpha(X, y, w, groups, n_splits=5) -> float:
    gkf = GroupKFold(n_splits=n_splits)
    scores = np.zeros(len(ALPHAS))
    for a_i, alpha in enumerate(ALPHAS):
        fold_err = []
        for tr, te in gkf.split(X, y, groups):
            m = Ridge(alpha=alpha, solver=SOLVER, fit_intercept=True)
            m.fit(X[tr], y[tr], sample_weight=w[tr])
            fold_err.append(wmse(y[te], m.predict(X[te]), w[te]))
        scores[a_i] = float(np.mean(fold_err))
        LOG.info("  α=%9.1f  CV wMSE=%.4f", alpha, scores[a_i])
    best = ALPHAS[int(np.argmin(scores))]
    LOG.info("selected α=%.1f", best)
    return best


def fit_coefs(X, y, w, alpha) -> np.ndarray:
    m = Ridge(alpha=alpha, solver=SOLVER, fit_intercept=True)
    m.fit(X, y, sample_weight=w)
    return m.coef_


def bootstrap_ci(X, y, w, groups, alpha, n_players, B, seed=42):
    """Block bootstrap by game: resample games with replacement, refit, collect
    ORAPM+DRAPM totals. Returns (lo, hi) 95% percentile arrays over players."""
    if B <= 0:
        return None, None
    rng = np.random.default_rng(seed)
    uniq = np.unique(groups)
    # map each game to its row indices once
    idx_by_game = {g: np.where(groups == g)[0] for g in uniq}
    totals = np.empty((B, n_players))
    for b in range(B):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        rows = np.concatenate([idx_by_game[g] for g in pick])
        coef = fit_coefs(X[rows], y[rows], w[rows], alpha)
        totals[b] = coef[:n_players] - coef[n_players:]   # ORAPM + (-DEF)
        if (b + 1) % 25 == 0:
            LOG.info("  bootstrap %d/%d", b + 1, B)
    lo = np.percentile(totals, 2.5, axis=0)
    hi = np.percentile(totals, 97.5, axis=0)
    return lo, hi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", type=float, default=None,
                    help="skip CV and use this λ")
    ap.add_argument("--bootstrap", type=int, default=0,
                    help="number of bootstrap resamples for CIs (0=skip; slow)")
    ap.add_argument("--min-poss", type=int, default=MIN_POSS)
    ap.add_argument("--min-games", type=int, default=0,
                    help="minimum games played (Olivo uses 50)")
    ap.add_argument("--prefix", default="rapm",
                    help="design prefix, e.g. --prefix rapm_olivo")
    ap.add_argument("--out", default=None,
                    help="output stem; defaults to <prefix>_baseline")
    args = ap.parse_args()
    out_stem = args.out or f"{args.prefix}_baseline"

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    X, y, w, groups = load(args.prefix)
    players = pl.read_parquet(f"warehouse/{args.prefix}_players.parquet").sort("col")
    n_players = players.height
    assert X.shape[1] == 2 * n_players, "design/player-index mismatch"

    alpha = args.alpha or select_alpha(X, y, w, groups)
    coef = fit_coefs(X, y, w, alpha)
    orapm = coef[:n_players]
    drapm = -coef[n_players:]                 # sign flip: positive = good defense
    total = orapm + drapm

    # possessions on court per player (off + def) from the design weights
    w_col = X.T @ w
    poss = (w_col[:n_players] + w_col[n_players:])

    lo, hi = bootstrap_ci(X, y, w, groups, alpha, n_players, args.bootstrap)

    keep_cols = ["player_id"] + (["n_games"] if "n_games" in players.columns else [])
    out = players.select(keep_cols).with_columns(
        pl.Series("poss", poss),
        pl.Series("ORAPM", orapm),
        pl.Series("DRAPM", drapm),
        pl.Series("RAPM", total),
    )
    if lo is not None:
        out = out.with_columns(pl.Series("RAPM_lo", lo), pl.Series("RAPM_hi", hi))

    # attach a readable name + season range (v2 map is keyed on (name, season),
    # so pick each id's most-frequent name and its career span in this dataset)
    try:
        m = pl.read_parquet(ID_MAP)
        n_col = "n_rows" if "n_rows" in m.columns else "n_pbp_rows"
        names = (m.group_by("player_id", "name").agg(pl.col(n_col).sum().alias("n"))
                 .sort("n", descending=True)
                 .group_by("player_id").first()
                 .select("player_id", "name"))
        spans = (m.group_by("player_id")
                 .agg(pl.col("season").min().alias("first_season"),
                      pl.col("season").max().alias("last_season")))
        out = out.join(names, on="player_id", how="left")
        out = out.join(spans, on="player_id", how="left")
    except Exception as exc:  # noqa: BLE001
        LOG.warning("could not attach names from %s (%s) — leaderboard will show "
                    "ids only", ID_MAP, exc)

    out = out.filter(pl.col("poss") >= args.min_poss)
    if args.min_games and "n_games" in out.columns:
        n_before = out.height
        out = out.filter(pl.col("n_games") >= args.min_games)
        LOG.info("min-games=%d filter: %d -> %d players", args.min_games,
                 n_before, out.height)
    out = out.sort("RAPM", descending=True)

    # readable column order
    front = [c for c in ("name", "player_id", "first_season", "last_season",
                         "n_games", "poss", "ORAPM", "DRAPM", "RAPM",
                         "RAPM_lo", "RAPM_hi")
             if c in out.columns]
    out = out.select(front + [c for c in out.columns if c not in front])

    # sanity: RAPM should center near 0 and top values land ~ +4..+7 /100
    LOG.info("leaderboard: %d players ≥ %d poss | RAPM mean=%.2f sd=%.2f "
             "min=%.2f max=%.2f (α=%.1f)", out.height, args.min_poss,
             out["RAPM"].mean(), out["RAPM"].std(), out["RAPM"].min(),
             out["RAPM"].max(), alpha)

    with pl.Config(tbl_rows=15, fmt_str_lengths=30, tbl_width_chars=180):
        LOG.info("TOP 15 by RAPM:\n%s", out.head(15))
        LOG.info("BOTTOM 5 by RAPM:\n%s", out.tail(5))

    out.write_parquet(f"warehouse/{out_stem}.parquet")
    out.write_csv(f"warehouse/{out_stem}.csv")
    LOG.info("wrote warehouse/%s.parquet and .csv", out_stem)
    LOG.info("Olivo (2024) sanity check: eyeball top-15 names + O/D magnitudes "
             "against the paper before trusting anything downstream.")


if __name__ == "__main__":
    main()