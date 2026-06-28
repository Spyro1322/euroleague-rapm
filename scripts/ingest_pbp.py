"""
ingest_pbp.py  —  O1 ETL persistence  (the step Week 1 deferred)
================================================================
Pulls validated lineup PBP for every *played* game and writes it to canonical
partitioned Parquet. This is the source `warehouse.pbp_lineups` (and therefore
pbp_clean / pbp_poss) reads from. Runs on YOUR machine — the live Euroleague API
is firewalled from the sandbox.

Resume-safe: a game whose Parquet already exists is skipped, so you can Ctrl-C
and re-run, or pull season-by-season over several sittings without re-fetching.

USAGE
    python scripts/ingest_pbp.py --seasons 2023                # one season (start here)
    python scripts/ingest_pbp.py --seasons 2007-2025           # full range
    python scripts/ingest_pbp.py --seasons 2023 --overwrite    # force re-pull

OUTPUT
    data/pbp_lineups/season=<YYYY>/gamecode=<NNNN>.parquet      (one file per game)

NOTE on 2025-26: `played == True` filters out unplayed fixtures, so re-running
this season weekly picks up newly-completed games only — this is your auto-refresh hook.
"""
from __future__ import annotations
import argparse
import logging
import time
from pathlib import Path

import pandas as pd
from euroleague_api.play_by_play_data import PlayByPlay

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")

OUT = Path("data/pbp_lineups")


def parse_seasons(spec: str) -> list[int]:
    """'2023' -> [2023] ; '2007-2025' -> [2007..2025]."""
    if "-" in spec:
        lo, hi = (int(x) for x in spec.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(spec)]


def ingest_season(client: PlayByPlay, season: int, overwrite: bool, sleep: float) -> dict:
    games = client.get_gamecodes_season(season)          # gameCode + played flag
    played = games.loc[games["played"], "gameCode"].astype(int).tolist()
    log.info("season %d — %d played games", season, len(played))

    done = skipped = failed = 0
    for gc in played:
        dest = OUT / f"season={season}" / f"gamecode={gc}.parquet"
        if dest.exists() and not overwrite:
            skipped += 1
            continue
        try:
            df = client.get_game_pbp_data_lineups(season=season, gamecode=gc, validate=True)
            if df is None or df.empty:
                log.warning("  game %d: empty PBP, skipped", gc)
                failed += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(dest, index=False)             # pyarrow handles list lineup cols
            done += 1
            if done % 25 == 0:
                log.info("  %d written (season %d)…", done, season)
            if sleep:
                time.sleep(sleep)
        except Exception as e:                            # transient API/JSON errors → log, continue
            log.error("  game %d failed: %s", gc, e)
            failed += 1
    log.info("season %d done — %d written, %d already present, %d failed",
             season, done, skipped, failed)
    return {"season": season, "written": done, "skipped": skipped, "failed": failed}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", required=True, help="'2023' or '2007-2025'")
    ap.add_argument("--overwrite", action="store_true", help="re-pull existing games")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between requests")
    a = ap.parse_args()

    client = PlayByPlay()        # competition='E' (Euroleague)
    summary = [ingest_season(client, s, a.overwrite, a.sleep) for s in parse_seasons(a.seasons)]

    tot = sum(r["written"] for r in summary)
    n_files = sum(1 for _ in OUT.rglob("*.parquet"))
    log.info("INGEST COMPLETE — %d new games this run, %d game-files on disk total",
             tot, n_files)
    if any(r["failed"] for r in summary):
        log.warning("some games failed — re-run the same command to retry only those (resume-safe)")


if __name__ == "__main__":
    main()
