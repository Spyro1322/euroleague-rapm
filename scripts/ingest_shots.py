"""
ingest_shots.py — O1, shot feed for the play-context tagger
===========================================================
Pulls the Points feed (ShotData.get_game_shot_data) for every played game and
writes canonical partitioned Parquet, mirroring ingest_pbp.py. The tagger needs
FASTBREAK / SECOND_CHANCE / COORD_X / COORD_Y / ACTION from this feed.

    python scripts/ingest_shots.py --seasons 2023        # start here
    python scripts/ingest_shots.py --seasons 2007-2025   # full range

OUTPUT
    data/shots/season=<YYYY>/gamecode=<NNNN>.parquet

The final coverage report is the point of running one season first: it tells you
which seasons actually carry shot coordinates. The Points feed is not guaranteed
to have COORD_X/Y populated for the oldest seasons — if early seasons come back
coordinate-sparse, the location-based buckets degrade gracefully (the tagger
falls back to ACTION codes), but you want to KNOW the coverage before modelling.
"""
from __future__ import annotations
import argparse
import logging
from pathlib import Path

import polars as pl
from euroleague_api.shot_data import ShotData

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("shots")
OUT = Path("data/shots")


def parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        lo, hi = (int(x) for x in spec.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(spec)]


def ingest_season(client: ShotData, season: int, overwrite: bool) -> None:
    games = client.get_gamecodes_season(season)
    played = games.loc[games["played"], "gameCode"].astype(int).tolist()
    log.info("season %d — %d played games", season, len(played))
    done = skipped = empty = failed = 0
    for gc in played:
        dest = OUT / f"season={season}" / f"gamecode={gc}.parquet"
        if dest.exists() and not overwrite:
            skipped += 1
            continue
        try:
            df = client.get_game_shot_data(season=season, gamecode=gc)
            if df is None or df.empty:
                empty += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(dest, index=False)
            done += 1
        except Exception as e:
            log.error("  game %d failed: %s", gc, e)
            failed += 1
    log.info("season %d — %d written, %d present, %d empty, %d failed",
             season, done, skipped, empty, failed)


def coverage_report() -> None:
    """Per-season: games on disk, total shots, and % of shots carrying coordinates
    and the FASTBREAK / SECOND_CHANCE flags. Defensive about column presence."""
    files = sorted(OUT.rglob("*.parquet"))
    if not files:
        log.warning("no shot files on disk")
        return
    df = pl.read_parquet(files)
    cols = set(df.columns)
    log.info("── coverage by season (shots on disk) ──")
    exprs = [pl.len().alias("shots"),
             pl.col("Gamecode").n_unique().alias("games")]
    if {"COORD_X", "COORD_Y"} <= cols:
        exprs.append((pl.col("COORD_X").is_not_null() & (pl.col("COORD_X") != 0))
                     .mean().alias("pct_coords"))
    for flag in ("FASTBREAK", "SECOND_CHANCE"):
        if flag in cols:
            exprs.append(pl.col(flag).is_not_null().mean().alias(f"pct_{flag.lower()}"))
    rep = df.group_by("Season").agg(exprs).sort("Season")
    with pl.Config(tbl_rows=20):
        print(rep)
    missing = {"COORD_X", "COORD_Y", "FASTBREAK", "SECOND_CHANCE", "ACTION", "NUM_ANOT"} - cols
    if missing:
        log.warning("expected Points-feed columns NOT found: %s — tagger field config "
                    "must be adjusted to the real names", sorted(missing))
    print("\nColumns present:", sorted(cols))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", required=True, help="'2023' or '2007-2025'")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    client = ShotData()
    for s in parse_seasons(a.seasons):
        ingest_season(client, s, a.overwrite)
    coverage_report()


if __name__ == "__main__":
    main()
