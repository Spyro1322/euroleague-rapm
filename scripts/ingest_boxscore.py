#!/usr/bin/env python3
"""
scripts/ingest_boxscore.py  —  Week 3, action 1a (coverage backstop for the ID map).
REWRITTEN after a 429 rate-limit storm exposed a silent-data-loss path.

WHY THIS DOESN'T USE get_players_boxscore_stats_single_season
-------------------------------------------------------------
euroleague_api 0.1.1's season wrapper calls utils.get_data_over_collection_of_games,
which catches HTTPError per game and logs "Skip and continue" — the exception never
reaches the caller. A season rate-limited into 90% failures returns a DataFrame that
is indistinguishable from a complete one. There is no retry and no backoff.

So this script drives the per-game endpoint itself:
  * own retry with exponential backoff + Retry-After on 429/5xx
  * ONE parquet shard PER GAME  → resume granularity is the game, not the season
  * a season is only marked complete (_SUCCESS) when every played gamecode has a
    shard; otherwise the misses are written to a _MISSING.csv and the season stays
    resumable. Re-running fills only the holes.

Run SOLO (do not run concurrently with ingest_shots.py — that is what caused the
429s):
    python scripts/ingest_boxscore.py --start 2007 --end 2025
    python scripts/ingest_boxscore.py --start 2007 --end 2025 --verify-only
"""
from __future__ import annotations
import argparse
import logging
import random
import sys
import time
from pathlib import Path

import pandas as pd
from requests.exceptions import HTTPError
from euroleague_api.boxscore_data import BoxScoreData

COMPETITION = "E"
OUT_DIR = Path("landing/boxscore_players")
LOG = logging.getLogger("ingest_boxscore")

# --- politeness / backoff ----------------------------------------------------
THROTTLE = 0.35          # seconds between successful requests (~3 req/s)
MAX_RETRIES = 6
BACKOFF_BASE = 2.0       # 2,4,8,16,32,64s + jitter
COOLDOWN_AFTER_429 = 30  # extra pause once the API has started rate-limiting


def game_shard(season: int, gamecode: int) -> Path:
    return OUT_DIR / f"season={season}" / f"game_{gamecode:05d}.parquet"


def season_dir(season: int) -> Path:
    return OUT_DIR / f"season={season}"


def _retry_after(exc: HTTPError) -> float | None:
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    val = resp.headers.get("Retry-After")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def fetch_game(bx: BoxScoreData, season: int, gamecode: int) -> pd.DataFrame | None:
    """Fetch one game's player boxscore with retry/backoff. Returns None on
    permanent failure (caller records it as MISSING — never silently dropped)."""
    for attempt in range(MAX_RETRIES):
        try:
            df = bx.get_players_boxscore_stats(season=season, gamecode=gamecode)
            time.sleep(THROTTLE)
            return df
        except HTTPError as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code == 404:
                LOG.debug("s%s g%s: 404 (not played / no feed)", season, gamecode)
                return None
            if code == 429 or (code is not None and 500 <= code < 600):
                wait = _retry_after(exc) or (BACKOFF_BASE ** attempt)
                wait += random.uniform(0, 1.0)
                if code == 429:
                    wait += COOLDOWN_AFTER_429
                LOG.warning("s%s g%s: HTTP %s — backing off %.1fs (attempt %d/%d)",
                            season, gamecode, code, wait, attempt + 1, MAX_RETRIES)
                time.sleep(wait)
                continue
            LOG.error("s%s g%s: HTTP %s — giving up", season, gamecode, code)
            return None
        except Exception as exc:  # noqa: BLE001
            wait = (BACKOFF_BASE ** attempt) + random.uniform(0, 1.0)
            LOG.warning("s%s g%s: %s — retry in %.1fs (attempt %d/%d)",
                        season, gamecode, exc, wait, attempt + 1, MAX_RETRIES)
            time.sleep(wait)
    LOG.error("s%s g%s: exhausted %d retries — recorded MISSING",
              season, gamecode, MAX_RETRIES)
    return None


def played_gamecodes(bx: BoxScoreData, season: int) -> list[int]:
    df = bx.get_gamecodes_season(season)
    df = df[df["played"]]
    return sorted(df["gameCode"].astype(int).unique().tolist())


def ingest_season(bx: BoxScoreData, season: int, overwrite: bool,
                  verify_only: bool) -> tuple[int, int]:
    sd = season_dir(season)
    sd.mkdir(parents=True, exist_ok=True)
    success_marker = sd / "_SUCCESS"

    if success_marker.exists() and not overwrite and not verify_only:
        LOG.info("season %s: complete (_SUCCESS present), skipping", season)
        return (0, 0)

    try:
        expected = played_gamecodes(bx, season)
    except Exception as exc:  # noqa: BLE001
        LOG.error("season %s: could not list gamecodes (%s) — season SKIPPED, "
                  "not marked complete", season, exc)
        return (0, -1)

    have = {int(p.stem.split("_")[1]) for p in sd.glob("game_*.parquet")}
    todo = [g for g in expected if g not in have] if not overwrite else expected

    LOG.info("season %s: %d played games | %d present | %d to fetch",
             season, len(expected), len(have), len(todo))

    if verify_only:
        missing = [g for g in expected if g not in have]
        _finalize(sd, season, expected, have, missing, write_marker=False)
        return (len(have), len(missing))

    fetched, missing = 0, []
    for i, gc in enumerate(todo, 1):
        df = fetch_game(bx, season, gc)
        if df is None or df.empty:
            missing.append(gc)
            continue
        if "Player_ID" in df.columns:
            df = df[df["Player_ID"].notna()
                    & (df["Player_ID"].astype(str).str.strip() != "")]
        if df.empty:
            missing.append(gc)
            continue
        df.to_parquet(game_shard(season, gc), index=False)
        fetched += 1
        if i % 25 == 0:
            LOG.info("season %s: %d/%d fetched", season, i, len(todo))

    have = {int(p.stem.split("_")[1]) for p in sd.glob("game_*.parquet")}
    missing = [g for g in expected if g not in have]
    _finalize(sd, season, expected, have, missing, write_marker=True)
    return (fetched, len(missing))


def _finalize(sd: Path, season: int, expected: list[int], have: set[int],
              missing: list[int], write_marker: bool) -> None:
    miss_file = sd / "_MISSING.csv"
    success_marker = sd / "_SUCCESS"
    if missing:
        pd.DataFrame({"season": season, "gamecode": missing}).to_csv(
            miss_file, index=False)
        if success_marker.exists():
            success_marker.unlink()
        LOG.error("season %s: INCOMPLETE — %d/%d games missing → %s "
                  "(re-run to fill; season NOT marked complete)",
                  season, len(missing), len(expected), miss_file)
    else:
        if miss_file.exists():
            miss_file.unlink()
        if write_marker:
            success_marker.write_text(f"{len(expected)} games\n")
        LOG.info("season %s: COMPLETE — %d/%d games ✔",
                 season, len(have), len(expected))


def main() -> None:
    global THROTTLE
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2007)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--verify-only", action="store_true",
                    help="report completeness per season, fetch nothing")
    ap.add_argument("--throttle", type=float, default=THROTTLE)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    THROTTLE = args.throttle

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bx = BoxScoreData(competition=COMPETITION)

    incomplete = []
    for season in range(args.start, args.end + 1):
        try:
            _, n_missing = ingest_season(bx, season, args.overwrite,
                                         args.verify_only)
            if n_missing != 0:
                incomplete.append(season)
        except KeyboardInterrupt:
            LOG.warning("interrupted — per-game shards on disk are safe, "
                        "re-run to resume")
            sys.exit(130)
        except Exception as exc:  # noqa: BLE001
            LOG.error("season %s FAILED: %s", season, exc)
            incomplete.append(season)

    if incomplete:
        LOG.error("INCOMPLETE SEASONS: %s — re-run to fill holes before "
                  "build_player_id_map.py", incomplete)
        sys.exit(1)
    LOG.info("all seasons complete. shards under %s", OUT_DIR.resolve())


if __name__ == "__main__":
    main()