"""
ingest_shots.py — O1, shot feed for the play-context tagger
===========================================================
Pulls the Points feed (ShotData.get_game_shot_data) for every played game and
writes canonical partitioned Parquet, mirroring ingest_pbp.py. The tagger needs
FASTBREAK / SECOND_CHANCE / COORD_X / COORD_Y / ACTION from this feed.

    python scripts/ingest_shots.py --seasons 2023        # start here
    python scripts/ingest_shots.py --seasons 2007-2025   # full range
    python scripts/ingest_shots.py --seasons 2007-2025 --retry-only  # only redo failed games

OUTPUT
    data/shots/season=<YYYY>/gamecode=<NNNN>.parquet
    data/shots/season=<YYYY>/_SUCCESS               (written iff zero failures that season)
    data/shots/season=<YYYY>/_MISSING.csv            (gamecode,error — failed games, if any)

RATE LIMITING (added — the original script had none, and the live API 429s hard
under back-to-back requests with no cooldown once tripped):
    - A minimum delay is enforced between every network call (season-level AND
      per-game), not just a reactive retry, because once the API starts 429ing
      here it appears to stay rate-limited for a while rather than recovering
      immediately — proactive throttling matters more than retry alone.
    - Every network call goes through retry_with_backoff: on HTTP 429, sleeps
      (respecting a Retry-After header if the API sends one, else exponential
      backoff + jitter) and retries up to MAX_RETRIES times before giving up
      on that one call.
    - A season that still fails after retries no longer kills the whole
      multi-season run: the season loop catches and logs, then continues.

The final coverage report is the point of running one season first: it tells you
which seasons actually carry shot coordinates. The Points feed is not guaranteed
to have COORD_X/Y populated for the oldest seasons — if early seasons come back
coordinate-sparse, the location-based buckets degrade gracefully (the tagger
falls back to ACTION codes), but you want to KNOW the coverage before modelling.
"""
from __future__ import annotations
import argparse
import csv
import logging
import random
import time
from pathlib import Path

import polars as pl
import requests
from euroleague_api.shot_data import ShotData

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("shots")
OUT = Path("data/shots")

# --- rate limiting / backoff config -----------------------------------------
REQUEST_DELAY_S = 1.5      # floor delay between EVERY network call, success or not
MAX_RETRIES = 6
BASE_BACKOFF_S = 5.0       # first retry sleep; doubles each subsequent attempt
MAX_BACKOFF_S = 120.0


def retry_with_backoff(fn, *args, **kwargs):
    """Call fn(*args, **kwargs); on HTTP 429 sleep (Retry-After if present, else
    exponential backoff + jitter) and retry up to MAX_RETRIES times. Always
    enforces REQUEST_DELAY_S after the call (success or final failure) so the
    next request in the loop doesn't immediately re-trigger the limit."""
    attempt = 0
    while True:
        try:
            result = fn(*args, **kwargs)
            time.sleep(REQUEST_DELAY_S)
            return result
        except requests.exceptions.HTTPError as e:
            resp = e.response
            if resp is not None and resp.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_s = float(retry_after)
                    except ValueError:
                        sleep_s = BASE_BACKOFF_S * (2 ** attempt)
                else:
                    sleep_s = min(BASE_BACKOFF_S * (2 ** attempt), MAX_BACKOFF_S)
                sleep_s += random.uniform(0, sleep_s * 0.2)  # jitter
                log.warning("  429 (attempt %d/%d) — sleeping %.1fs", attempt + 1,
                            MAX_RETRIES, sleep_s)
                time.sleep(sleep_s)
                attempt += 1
                continue
            time.sleep(REQUEST_DELAY_S)
            raise


def parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        lo, hi = (int(x) for x in spec.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(spec)]


def load_missing(season_dir: Path) -> set[int]:
    p = season_dir / "_MISSING.csv"
    if not p.exists():
        return set()
    with p.open() as f:
        return {int(row["gamecode"]) for row in csv.DictReader(f)}


def write_missing(season_dir: Path, failures: dict[int, str]) -> None:
    p = season_dir / "_MISSING.csv"
    if not failures:
        p.unlink(missing_ok=True)
        return
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gamecode", "error"])
        for gc, err in sorted(failures.items()):
            w.writerow([gc, err])


def ingest_season(client: ShotData, season: int, overwrite: bool, retry_only: bool) -> None:
    season_dir = OUT / f"season={season}"
    try:
        games = retry_with_backoff(client.get_gamecodes_season, season)
    except Exception as e:
        log.error("season %d — could not fetch gamecode list, skipping season: %s", season, e)
        return

    played = games.loc[games["played"], "gameCode"].astype(int).tolist()

    if retry_only:
        prior_missing = load_missing(season_dir)
        if not prior_missing:
            log.info("season %d — retry-only requested but no _MISSING.csv, nothing to do", season)
            return
        played = [gc for gc in played if gc in prior_missing]
        log.info("season %d — retry-only: %d previously-failed games", season, len(played))
    else:
        log.info("season %d — %d played games", season, len(played))

    done = skipped = empty = failed = 0
    failures: dict[int, str] = {}
    for gc in played:
        dest = season_dir / f"gamecode={gc}.parquet"
        if dest.exists() and not overwrite:
            skipped += 1
            continue
        try:
            df = retry_with_backoff(client.get_game_shot_data, season=season, gamecode=gc)
            if df is None or df.empty:
                empty += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(dest, index=False)
            done += 1
        except Exception as e:
            log.error("  game %d failed (after retries): %s", gc, e)
            failures[gc] = str(e)
            failed += 1

    # merge with any pre-existing missing list not addressed this run (e.g. a
    # non-retry-only run that skipped already-on-disk games)
    if not retry_only:
        carried = load_missing(season_dir) - set(played)
        for gc in carried:
            failures.setdefault(gc, "carried from prior run, not re-attempted")

    season_dir.mkdir(parents=True, exist_ok=True)
    write_missing(season_dir, failures)
    if not failures:
        (season_dir / "_SUCCESS").touch()
    else:
        (season_dir / "_SUCCESS").unlink(missing_ok=True)

    log.info("season %d — %d written, %d present, %d empty, %d failed%s",
             season, done, skipped, empty, failed,
             "" if not failures else f" (see {season_dir / '_MISSING.csv'})")


def coverage_report() -> None:
    """Per-season: games on disk, total shots, and % of shots carrying coordinates
    and the FASTBREAK / SECOND_CHANCE flags. Defensive about column presence."""
    files = sorted(OUT.rglob("*.parquet"))
    if not files:
        log.warning("no shot files on disk")
        return
    # Older seasons leave some flag columns (e.g. FASTBREAK) entirely null, so
    # polars infers them as Null there and String elsewhere — a plain
    # pl.read_parquet(files) then fails the vertical concat with a SchemaError.
    # Read per-file and diagonal-concat (union of columns, nulls filled), casting
    # everything to str first so a column that's Null in one file and String in
    # another reconciles cleanly. The report only needs presence/null-rate, so
    # stringifying loses nothing here.
    frames = []
    bad = 0
    for f in files:
        try:
            frames.append(pl.read_parquet(f).cast(pl.String, strict=False))
        except Exception as e:
            log.warning("  coverage: could not read %s: %s", f, e)
            bad += 1
    if not frames:
        log.warning("no readable shot files for coverage report")
        return
    if bad:
        log.warning("coverage report skipped %d unreadable file(s)", bad)
    df = pl.concat(frames, how="diagonal_relaxed")
    cols = set(df.columns)
    log.info("── coverage by season (shots on disk) ──")
    # Everything is str now; treat null OR empty-string OR "0"/"0.0" as "no coord".
    exprs = [pl.len().alias("shots"),
             pl.col("Gamecode").n_unique().alias("games")]
    if {"COORD_X", "COORD_Y"} <= cols:
        cx = pl.col("COORD_X")
        has_coord = cx.is_not_null() & (cx != "") & (cx != "0") & (cx != "0.0")
        exprs.append(has_coord.mean().alias("pct_coords"))
    for flag in ("FASTBREAK", "SECOND_CHANCE"):
        if flag in cols:
            fc = pl.col(flag)
            populated = fc.is_not_null() & (fc != "")
            exprs.append(populated.mean().alias(f"pct_{flag.lower()}"))
    rep = df.group_by("Season").agg(exprs).sort("Season")
    with pl.Config(tbl_rows=20):
        print(rep)
    missing = {"COORD_X", "COORD_Y", "FASTBREAK", "SECOND_CHANCE", "ACTION", "NUM_ANOT"} - cols
    if missing:
        log.warning("expected Points-feed columns NOT found: %s — tagger field config "
                    "must be adjusted to the real names", sorted(missing))
    print("\nColumns present:", sorted(cols))

    # surface any seasons with an unresolved _MISSING.csv so a coverage-report-only
    # run still tells you what's incomplete
    incomplete = sorted(OUT.glob("season=*/_MISSING.csv"))
    if incomplete:
        log.warning("seasons with unresolved failures (rerun with --retry-only): %s",
                    [str(p.parent.name) for p in incomplete])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", required=True, help="'2023' or '2007-2025'")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--retry-only", action="store_true",
                    help="only re-attempt games listed in each season's _MISSING.csv")
    a = ap.parse_args()
    client = ShotData()
    for s in parse_seasons(a.seasons):
        ingest_season(client, s, a.overwrite, a.retry_only)
    coverage_report()


if __name__ == "__main__":
    main()