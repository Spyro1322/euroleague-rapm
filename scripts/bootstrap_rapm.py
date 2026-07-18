#!/usr/bin/env python3
"""
bootstrap_rapm.py -- cluster (game-level) bootstrap CIs for a fitted ridge RAPM.

Run ONCE per PRESENTED leaderboard, after the point fit is validated:
    rapm_baseline  -> Ch4 all-time career leaderboard CIs   (heavy: overnight)
    rapm_dash      -> Tab 1 current-form CIs                 (5-season window, faster)
Skip rapm_eval (Ch7 uses RMSE / point estimates, not CIs).

Method
------
Cluster bootstrap on the CV group key (Season, Gamecode): resample the groups
WITH replacement to a sample of the same #groups, stack their rows (a group drawn
k times contributes its rows k times), refit the SAME weighted ridge at the FIXED
alpha selected for this prefix, and take 2.5 / 97.5 percentiles of each player's
ORAPM / DRAPM / RAPM across B refits.

Conventions preserved from build_rapm_design / fit_ridge_rapm:
    ORAPM = off coef ; DRAPM = -(def coef) so positive = good defence ;
    RAPM  = ORAPM + DRAPM. y = luck-adjusted pts/100 ; row weight = off possessions.
CIs condition on the fixed alpha (standard); a player appearing in few sampled
games naturally gets wider CIs -- that is correct, not a bug.

------------------------------------------------------------------------------
I/O TO CONFIRM against build_rapm_design.py / fit_ridge_rapm.py output.
Only the four load_* functions below touch disk. Adjust names/columns to match
your artifacts, then never touch the rest. Expected for a given --prefix:

  warehouse/{prefix}_design.npz    scipy CSR X, rows=obs, cols=player effects
  warehouse/{prefix}_rows.parquet  one row per obs: y, weight, Season, Gamecode
  warehouse/{prefix}_cols.parquet  one row per column: col_index, end, player_id
  warehouse/{prefix}.parquet       point fit per player:
                                     player_id, player, poss, ORAPM, DRAPM, RAPM
------------------------------------------------------------------------------
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge


# --------------------------------------------------------------------------- #
# I/O  (the only assumptions in the file -- confirm against your build script) #
# --------------------------------------------------------------------------- #
def load_design(wh: Path, prefix: str) -> sparse.csr_matrix:
    X = sparse.load_npz(wh / f"{prefix}_design.npz").tocsr()
    return X


def load_rows(wh: Path, prefix: str) -> pd.DataFrame:
    # y (luck-adjusted pts/100), weight (offensive possessions), group key columns
    df = pd.read_parquet(wh / f"{prefix}_rows.parquet")
    need = {"y", "weight", "Season", "Gamecode"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"[rows] missing columns {missing} -- edit load_rows() to map them.")
    return df


def load_cols(wh: Path, prefix: str) -> pd.DataFrame:
    # col_index (0..n_cols-1), end in {'off','def'}, player_id
    df = pd.read_parquet(wh / f"{prefix}_cols.parquet")
    need = {"col_index", "end", "player_id"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"[cols] missing columns {missing} -- edit load_cols() to map them.")
    return df.sort_values("col_index").reset_index(drop=True)


def load_point_fit(wh: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_parquet(wh / f"{prefix}.parquet")
    if "player_id" not in df.columns:
        sys.exit("[fit] point-fit table needs a player_id column -- edit load_point_fit().")
    return df


# --------------------------------------------------------------------------- #
# Bootstrap                                                                    #
# --------------------------------------------------------------------------- #
def player_effects(coef: np.ndarray, cols: pd.DataFrame) -> pd.DataFrame:
    """Map a coefficient vector to per-player ORAPM / DRAPM / RAPM."""
    tmp = cols.copy()
    tmp["coef"] = coef[tmp["col_index"].to_numpy()]
    piv = tmp.pivot_table(index="player_id", columns="end", values="coef",
                          aggfunc="first").fillna(0.0)
    orapm = piv.get("off", pd.Series(0.0, index=piv.index))
    drapm = -piv.get("def", pd.Series(0.0, index=piv.index))  # sign flip
    out = pd.DataFrame({"ORAPM": orapm, "DRAPM": drapm})
    out["RAPM"] = out["ORAPM"] + out["DRAPM"]
    return out


def refit(X, y, w, alpha, fit_intercept, solver):
    m = Ridge(alpha=alpha, fit_intercept=fit_intercept, solver=solver,
              max_iter=5000, tol=1e-4)
    m.fit(X, y, sample_weight=w)
    return np.asarray(m.coef_).ravel()


def run(args):
    wh = Path(args.warehouse)
    X = load_design(wh, args.prefix)
    rows = load_rows(wh, args.prefix)
    cols = load_cols(wh, args.prefix)
    fit = load_point_fit(wh, args.prefix)

    if X.shape[0] != len(rows):
        sys.exit(f"row mismatch: X has {X.shape[0]} rows, rows.parquet has {len(rows)}.")
    if X.shape[1] != len(cols):
        sys.exit(f"col mismatch: X has {X.shape[1]} cols, cols.parquet has {len(cols)}.")

    y = rows["y"].to_numpy(dtype=np.float64)
    w = rows["weight"].to_numpy(dtype=np.float64)

    # group key -> row indices
    grp = rows.groupby(["Season", "Gamecode"], sort=False).indices  # dict -> ndarray
    group_rows = list(grp.values())
    n_groups = len(group_rows)
    print(f"[{args.prefix}] X={X.shape[0]}x{X.shape[1]}  players={fit['player_id'].nunique()}"
          f"  groups={n_groups}  alpha={args.alpha}  B={args.n_boot}")

    players = fit["player_id"].to_numpy()
    B = args.n_boot
    boot = {k: np.full((B, len(players)), np.nan) for k in ("ORAPM", "DRAPM", "RAPM")}
    pidx = pd.Index(players)

    rng = np.random.default_rng(args.seed)
    t0 = time.time()
    for b in range(B):
        pick = rng.integers(0, n_groups, size=n_groups)     # groups w/ replacement
        idx = np.concatenate([group_rows[g] for g in pick])
        coef = refit(X[idx], y[idx], w[idx], args.alpha,
                     args.fit_intercept, args.solver)
        eff = player_effects(coef, cols).reindex(pidx)       # align to point-fit order
        for k in boot:
            boot[k][b] = eff[k].to_numpy()
        if (b + 1) % 25 == 0 or b + 1 == B:
            el = time.time() - t0
            eta = el / (b + 1) * (B - b - 1)
            print(f"  {b+1:4d}/{B}  elapsed {el/60:5.1f}m  eta {eta/60:5.1f}m", flush=True)

    out = fit.copy()
    for k in ("ORAPM", "DRAPM", "RAPM"):
        lo = np.nanpercentile(boot[k], 2.5, axis=0)
        hi = np.nanpercentile(boot[k], 97.5, axis=0)
        out[f"{k}_lo"] = lo
        out[f"{k}_hi"] = hi
        out[f"{k}_se"] = np.nanstd(boot[k], axis=0, ddof=1)

    out_pq = wh / f"{args.prefix}_boot.parquet"
    out.to_parquet(out_pq, index=False)
    out.to_csv(wh / f"{args.prefix}_boot.csv", index=False)
    print(f"wrote {out_pq}  ({len(out)} players, {B} resamples, "
          f"{(time.time()-t0)/60:.1f}m total)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", required=True,
                    help="rapm_baseline | rapm_dash (the fits you PRESENT with CIs)")
    ap.add_argument("--alpha", type=float, required=True,
                    help="CV-selected alpha for THIS prefix (e.g. 1995.3 for luck-adj "
                         "all-time; the windowed fits pick their own -- read fit output)")
    ap.add_argument("--n-boot", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--warehouse", default="warehouse")
    ap.add_argument("--solver", default="lsqr",
                    help="sparse-safe ridge solver: lsqr | sparse_cg")
    ap.add_argument("--fit-intercept", dest="fit_intercept", action="store_true",
                    default=True, help="MATCH fit_ridge_rapm.py's intercept handling")
    ap.add_argument("--no-fit-intercept", dest="fit_intercept", action="store_false")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
