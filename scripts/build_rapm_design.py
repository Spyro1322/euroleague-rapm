#!/usr/bin/env python3
"""
scripts/build_rapm_design.py  —  Week 3, action 2a.

Turns stints_ids.parquet into a sparse offense/defense RAPM design matrix.

Model observations: each stint contributes up to TWO rows, one per offensive team.
    y      = points scored by the offense per 100 possessions on that stint
    weight = offensive possessions on that stint (row weight)
    columns: 2 per player — off_<id> and def_<id>
        offense=home row → off_<home player>=+1, def_<away player>=+1
Coefficient reading (done in fit_ridge_rapm.py):
    ORAPM = coef(off_<id>)            (points added / 100 on offense)
    DRAPM = -coef(def_<id>)           (points prevented / 100 on defense; sign flip
                                       so that positive = good defender)
    Total = ORAPM + DRAPM

Outputs (npz + parquet sidecar):
    warehouse/rapm_design.npz    X (csr), y, w, groups
    warehouse/rapm_players.parquet   col_index → player_id, off/def offset

Run after build_player_id_map.py, before fit_ridge_rapm.py.
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import polars as pl
import scipy.sparse as sp

LOG = logging.getLogger("rapm_design")

# ============================================================ CONFIG — verify these
# All names below VERIFIED against the real stints.parquet schema.
STINTS = "warehouse/stints_ids.parquet"
HOME_LINEUP_COL = "home_players"      # list[str] of home player_ids (post-remap)
AWAY_LINEUP_COL = "away_players"
HOME_PTS_COL = "home_pts"             # points scored BY home on this stint
AWAY_PTS_COL = "away_pts"
HOME_POSS_COL = "home_poss"           # offensive possessions BY home on this stint
AWAY_POSS_COL = "away_poss"
GAME_COL = "Gamecode"                 # season-scoped! NOT globally unique
SEASON_COL = "Season"
# Gamecode repeats across seasons (only ~402 distinct values over 19 seasons), so
# the CV / bootstrap group key MUST be the (Season, Gamecode) pair. Grouping on
# Gamecode alone would put ~19 different games in one group, leaking a game's
# stints across CV folds and destroying the bootstrap's block structure.
GAME_UID_MULT = 100_000               # game_uid = Season * MULT + Gamecode

# Drop stints whose five contains the same player twice. The Week-2 `lineup_ok`
# flag is all-True in stints.parquet and does NOT catch these (verified: 33
# stints have duplicated fives while lineup_ok=true everywhere), so distinctness
# is re-derived here rather than trusted.
ENFORCE_DISTINCT_FIVES = True

# Week-2 QC guard: 27/5039 games (0.54%) carry duplicated-player fives from the
# euroleague_api sub-matcher cascade. Those lineups are corrupt and MUST NOT enter
# the ridge columns. Set to None only if you deliberately want them in.
LINEUP_OK_COL = "lineup_ok"           # Boolean

# --- luck adjustment (optional, Week-3 baseline) ----------------------------
# Classic RAPM luck-adjusts by replacing realised points with EXPECTED points
# (e.g. 3P makes -> 3 * 3PA * league_avg_3P%). That must happen BEFORE points
# become a per-100 ratio, which is why it lives here, not in the fit step.
# Point these at columns your possession walker emits (expected points scored
# BY that team on the stint). Leave as None to fit on raw points.
HOME_XPTS_COL = "home_xpts"                   # e.g. "home_xpoints"
AWAY_XPTS_COL = "away_xpts"                   # e.g. "away_xpoints"

OUT_NPZ = Path("warehouse/rapm_design.npz")          # overridden by --prefix
OUT_PLAYERS = Path("warehouse/rapm_players.parquet")  # overridden by --prefix
PER = 100.0                           # points per-100-possessions scaling
# ============================================================================


def _need(df: pl.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        LOG.error("stints_ids.parquet missing %s. Actual columns: %s",
                  missing, df.columns)
        LOG.error("Edit the CONFIG block at the top of this file to match your "
                  "Week-2 stint schema.")
        sys.exit(2)


def build(seasons=None, prefix='rapm') -> None:
    out_npz = Path(f'warehouse/{prefix}_design.npz')
    out_players = Path(f'warehouse/{prefix}_players.parquet')
    df = pl.read_parquet(STINTS)
    _need(df, [HOME_LINEUP_COL, AWAY_LINEUP_COL, HOME_PTS_COL, AWAY_PTS_COL,
               HOME_POSS_COL, AWAY_POSS_COL, GAME_COL, SEASON_COL])

    if seasons is not None:
        lo, hi = seasons
        n_before = df.height
        df = df.filter((pl.col(SEASON_COL) >= lo) & (pl.col(SEASON_COL) <= hi))
        LOG.info("season window %d-%d: kept %d/%d stints", lo, hi, df.height,
                 n_before)

    # ---- Week-2 lineup_ok guard: drop corrupt (duplicated-player) fives -------
    if LINEUP_OK_COL and LINEUP_OK_COL in df.columns:
        n_before = df.height
        df = df.filter(pl.col(LINEUP_OK_COL))
        dropped = n_before - df.height
        LOG.info("lineup_ok guard: dropped %d/%d stints (%.2f%%), %d remain",
                 dropped, n_before, 100.0 * dropped / max(n_before, 1), df.height)

    # ---- distinctness re-derived (lineup_ok does NOT catch these) -------------
    if ENFORCE_DISTINCT_FIVES:
        n_before = df.height
        bad = (
            (pl.col(HOME_LINEUP_COL).list.n_unique()
             != pl.col(HOME_LINEUP_COL).list.len())
            | (pl.col(AWAY_LINEUP_COL).list.n_unique()
               != pl.col(AWAY_LINEUP_COL).list.len())
        )
        n_bad_games = df.filter(bad).select(
            (pl.col(SEASON_COL).cast(pl.Int64) * GAME_UID_MULT
             + pl.col(GAME_COL).cast(pl.Int64)).n_unique()
        ).item() if df.filter(bad).height else 0
        df = df.filter(~bad)
        dropped = n_before - df.height
        LOG.info("distinct-five guard: dropped %d/%d stints (%.3f%%) across %d "
                 "game(s); %d remain", dropped, n_before,
                 100.0 * dropped / max(n_before, 1), n_bad_games, df.height)
        if dropped == 0:
            LOG.info("  (no duplicated-player fives found)")

    # ---- composite game key: Gamecode is season-scoped ------------------------
    df = df.with_columns(
        (pl.col(SEASON_COL).cast(pl.Int64) * GAME_UID_MULT
         + pl.col(GAME_COL).cast(pl.Int64)).alias("_game_uid")
    )
    n_codes = df[GAME_COL].n_unique()
    n_games = df["_game_uid"].n_unique()
    LOG.info("group key: %d distinct Gamecode values → %d distinct "
             "(Season, Gamecode) games", n_codes, n_games)
    if n_games < 4000:
        LOG.warning("expected ~5039 games — check the group key")

    # luck adjustment: swap raw points for expected points if configured
    home_pts_col, away_pts_col = HOME_PTS_COL, AWAY_PTS_COL
    if HOME_XPTS_COL and AWAY_XPTS_COL:
        _need(df, [HOME_XPTS_COL, AWAY_XPTS_COL])
        home_pts_col, away_pts_col = HOME_XPTS_COL, AWAY_XPTS_COL
        LOG.info("luck adjustment ON — fitting on expected points (%s / %s)",
                 HOME_XPTS_COL, AWAY_XPTS_COL)
    else:
        LOG.info("luck adjustment OFF — fitting on raw points")

    # ---- games per player (for Olivo-style >=50 games filters) ---------------
    games_df = (
        pl.concat([
            df.select(pl.col(HOME_LINEUP_COL).alias("player_id"), pl.col("_game_uid")),
            df.select(pl.col(AWAY_LINEUP_COL).alias("player_id"), pl.col("_game_uid")),
        ]).explode("player_id").drop_nulls()
        .group_by("player_id").agg(pl.col("_game_uid").n_unique().alias("n_games"))
    )

    # ---- player index over every id appearing in any lineup -------------------
    all_ids = (
        pl.concat([
            df.select(pl.col(HOME_LINEUP_COL).list.explode().alias("pid")),
            df.select(pl.col(AWAY_LINEUP_COL).list.explode().alias("pid")),
        ])
        .drop_nulls()
        .unique()
        .sort("pid")
    )
    players = all_ids["pid"].to_list()
    n_players = len(players)
    pid_to_col = {pid: i for i, pid in enumerate(players)}
    OFF, DEF = 0, n_players            # column-block offsets
    n_cols = 2 * n_players
    LOG.info("%d unique players → %d design columns", n_players, n_cols)

    # ---- assemble COO triplets, two observations per stint --------------------
    rows_i: list[int] = []
    cols_j: list[int] = []
    y_list: list[float] = []
    w_list: list[float] = []
    grp_list: list[int] = []
    r = 0

    recs = df.select(
        HOME_LINEUP_COL, AWAY_LINEUP_COL, home_pts_col, away_pts_col,
        HOME_POSS_COL, AWAY_POSS_COL, "_game_uid",
    ).iter_rows()

    def emit(off_ids, def_ids, pts, poss, game, nonlocal_r):
        if poss is None or poss <= 0 or pts is None:
            return nonlocal_r
        for pid in off_ids:
            j = pid_to_col.get(pid)
            if j is not None:
                rows_i.append(nonlocal_r); cols_j.append(OFF + j)
        for pid in def_ids:
            j = pid_to_col.get(pid)
            if j is not None:
                rows_i.append(nonlocal_r); cols_j.append(DEF + j)
        y_list.append(PER * pts / poss)
        w_list.append(float(poss))
        grp_list.append(int(game))
        return nonlocal_r + 1

    for hl, al, hp, ap, hpo, apo, game in recs:
        hl = hl or []; al = al or []
        r = emit(hl, al, hp, hpo, game, r)   # home on offense
        r = emit(al, hl, ap, apo, game, r)   # away on offense

    n_obs = len(y_list)
    X = sp.coo_matrix(
        (np.ones(len(rows_i), dtype=np.float32),
         (np.asarray(rows_i), np.asarray(cols_j))),
        shape=(n_obs, n_cols),
    ).tocsr()

    # coo_matrix SUMS duplicate (row, col) pairs — a player appearing twice in a
    # five would silently become a 2.0 (two men on the floor). Guard explicitly.
    n_dupe = int((X.data > 1.0).sum())
    if n_dupe:
        LOG.error("%d design entries >1 (player counted twice) — clamping to 1.0. "
                  "This should be 0 after the distinct-five guard.", n_dupe)
        X.data[:] = np.minimum(X.data, 1.0)
    assert X.data.max() <= 1.0, "design matrix still has entries > 1"
    assert set(np.unique(X.data)) <= {1.0}, "design matrix is not 0/1"

    exp_nnz = 10 * n_obs
    LOG.info("design: %d observations, X nnz=%d (expected %d for 10 players/row; "
             "shortfall %d = short lineups)", n_obs, X.nnz, exp_nnz,
             exp_nnz - X.nnz)
    y = np.asarray(y_list, dtype=np.float64)
    w = np.asarray(w_list, dtype=np.float64)
    groups = np.asarray(grp_list, dtype=np.int64)

    LOG.info("design: mean y=%.2f/100, total poss=%.0f, %d CV/bootstrap groups",
             float(np.average(y, weights=w)), float(w.sum()),
             len(np.unique(groups)))

    out_npz.parent.mkdir(parents=True, exist_ok=True)
    sp.save_npz(out_npz.with_suffix('.X.npz'), X)
    np.savez(out_npz, y=y, w=w, groups=groups,
             x_path=str(out_npz.with_suffix('.X.npz')))
    pl.DataFrame({
        "col": list(range(n_players)),
        "player_id": players,
    }).with_columns(
        pl.lit(OFF).alias("off_offset"), pl.lit(DEF).alias("def_offset")
    ).join(games_df, on="player_id", how="left").write_parquet(out_players)
    LOG.info("wrote %s (+ .X.npz) and %s", out_npz, out_players)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default=None,
                    help="inclusive start-year window, e.g. 2018:2022 for "
                         "2018-19..2022-23 (Olivo's replication window)")
    ap.add_argument("--prefix", default="rapm",
                    help="output prefix, e.g. --prefix rapm_olivo")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    seasons = None
    if args.seasons:
        lo, hi = args.seasons.split(":")
        seasons = (int(lo), int(hi))
    build(seasons=seasons, prefix=args.prefix)


if __name__ == "__main__":
    main()