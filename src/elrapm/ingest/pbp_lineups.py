"""Thin ingestion wrapper: pull PBP+lineups for a season -> landing parquet.

Kept deliberately small; the heavy lifting (10-on-court reconstruction) lives in
euroleague_api. We only add: season-level batching, parquet write, and a guard
that refuses to silently land empty-lineup games (the older-season failure mode).
"""
from __future__ import annotations

import logging
from pathlib import Path

from euroleague_api.play_by_play_data import PlayByPlay

from ..config import COMPETITION, LANDING

log = logging.getLogger(__name__)


def ingest_season(season: int, out_dir: Path = LANDING, strict: bool = True) -> Path:
    pbp = PlayByPlay(competition=COMPETITION)
    df = pbp.get_game_pbp_data_lineups_single_season(season)

    if strict and not df.empty:
        empty = df["Lineup_A"].apply(lambda x: not x).mean()
        if empty > 0.0:
            log.warning(
                "season %s: %.1f%% of actions have empty lineups "
                "(missing boxscore IsStarter). Investigate before modelling.",
                season, 100 * empty,
            )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pbp_lineups_{season}.parquet"
    df.to_parquet(path, index=False)
    log.info("season %s -> %s (%d actions)", season, path, len(df))
    return path
