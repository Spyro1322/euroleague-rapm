#!/usr/bin/env python3
"""
Week-1 highest-leverage check
=============================

Empirically answer: does `euroleague_api` cleanly reconstruct the 10-on-court
lineup across the FULL 2007-08 -> 2025-26 range, or does it degrade in older
seasons?

Everything downstream (stint matrix, RAPM, play-type-conditional RAPM, synergy)
is built on `get_game_pbp_data_lineups`. That function derives the starting five
from boxscore `IsStarter==1` and walks PBP IN/OUT events forward. It has two
hard dependencies that are known to degrade in early seasons:
    1. boxscore must carry IsStarter  -> else lineups come back EMPTY (silently)
    2. PBP must carry consistent IN/OUT sub events matched by MARKERTIME+team

So "it ran without crashing" is NOT evidence it worked. This script measures the
things that actually matter, per season, on a random sample of played games:

    games_ok          fraction of sampled games that returned non-empty PBP
    boxscore_ok       fraction with a usable starting five (IsStarter present)
    valid_rate        mean of `validate_on_court_player` (1.0 = perfect)
    five_invariant    fraction of actions where BOTH teams had exactly 5 distinct
                      players on court (the strongest single quality signal)
    empty_lineup_rate fraction of actions with an empty reconstructed lineup

Output: one row per (season, gamecode) + a per-season summary, written to parquet
and printed. Use the per-season `valid_rate` / `five_invariant` curve to DECIDE
the real start of your usable season range (the open SCOPE issue in STATUS.md).

Run locally (needs network access to live.euroleague.net, which CI/sandboxes may
block):

    python scripts/validate_lineups.py --start 2007 --end 2025 \
        --games-per-season 5 --seed 42

Quick smoke test on three recent seasons:

    python scripts/validate_lineups.py --start 2023 --end 2025 --games-per-season 3
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

import pandas as pd

from euroleague_api.play_by_play_data import PlayByPlay
from euroleague_api.schedule import Schedule

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("validate_lineups")
log.setLevel(logging.INFO)


def lineup_sizes(df: pd.DataFrame) -> pd.Series:
    """For each action: True iff BOTH teams have exactly 5 distinct players."""
    def ok(row) -> bool:
        a, b = row.get("Lineup_A"), row.get("Lineup_B")
        if not isinstance(a, list) or not isinstance(b, list):
            return False
        return len(set(a)) == 5 and len(set(b)) == 5
    return df.apply(ok, axis=1)


def check_game(pbp: PlayByPlay, season: int, gamecode: int) -> dict:
    """Pull one game's PBP+lineups and compute quality metrics."""
    rec = {
        "season": season,
        "gamecode": gamecode,
        "games_ok": False,
        "boxscore_ok": False,
        "n_actions": 0,
        "valid_rate": float("nan"),
        "five_invariant": float("nan"),
        "empty_lineup_rate": float("nan"),
        "error": "",
    }
    try:
        df = pbp.get_game_pbp_data_lineups(season=season, gamecode=gamecode,
                                           validate=True)
    except Exception as exc:  # noqa: BLE001 — we want to record, not crash
        rec["error"] = f"{type(exc).__name__}: {exc}"
        return rec

    if df is None or df.empty:
        rec["error"] = "empty PBP"
        return rec

    rec["games_ok"] = True
    rec["n_actions"] = len(df)

    # empty lineups => boxscore IsStarter was missing/unusable for this game
    empty = df["Lineup_A"].apply(lambda x: not x) | \
        df["Lineup_B"].apply(lambda x: not x)
    rec["empty_lineup_rate"] = float(empty.mean())
    rec["boxscore_ok"] = bool((~empty).any())

    if "validate_on_court_player" in df.columns:
        rec["valid_rate"] = float(df["validate_on_court_player"].mean())

    rec["five_invariant"] = float(lineup_sizes(df).mean())
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=2007, help="first season start-year")
    ap.add_argument("--end", type=int, default=2025, help="last season start-year")
    ap.add_argument("--games-per-season", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--competition", default="E", choices=["E", "U"])
    ap.add_argument("--out", type=Path,
                    default=Path("data/validation/wk1_lineup_validation.parquet"))
    args = ap.parse_args()

    random.seed(args.seed)
    pbp = PlayByPlay(competition=args.competition)
    sched = Schedule(competition=args.competition)

    rows: list[dict] = []
    for season in range(args.start, args.end + 1):
        try:
            games = sched.get_gamecodes_season(season)
        except Exception as exc:  # noqa: BLE001
            log.warning("season %s: could not list gamecodes (%s)", season, exc)
            rows.append({"season": season, "gamecode": -1, "games_ok": False,
                         "error": f"schedule: {exc}"})
            continue

        played = games.loc[games.get("played", True) == True, "gameCode"].tolist()  # noqa: E712
        if not played:
            played = games["gameCode"].tolist()
        sample = random.sample(played, min(args.games_per_season, len(played)))

        for gc in sample:
            rec = check_game(pbp, season, int(gc))
            rows.append(rec)
            log.info(
                "season %s game %5d | ok=%s boxscore=%s valid=%.3f five=%.3f",
                season, gc, rec["games_ok"], rec["boxscore_ok"],
                rec["valid_rate"] if rec["valid_rate"] == rec["valid_rate"] else -1,
                rec["five_invariant"] if rec["five_invariant"] == rec["five_invariant"] else -1,
            )

    detail = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    detail.to_parquet(args.out, index=False)

    summary = (
        detail.groupby("season")
        .agg(
            n_games=("gamecode", "size"),
            games_ok=("games_ok", "mean"),
            boxscore_ok=("boxscore_ok", "mean"),
            valid_rate=("valid_rate", "mean"),
            five_invariant=("five_invariant", "mean"),
            empty_lineup_rate=("empty_lineup_rate", "mean"),
        )
        .round(3)
    )
    summary_path = args.out.with_name("wk1_lineup_validation_summary.parquet")
    summary.to_parquet(summary_path)

    pd.set_option("display.width", 120)
    print("\n=== Per-season lineup-reconstruction quality "
          f"({args.start}-{args.end}, {args.games_per_season} games/season) ===\n")
    print(summary.to_string())
    print(f"\nDetail : {args.out}")
    print(f"Summary: {summary_path}")
    print(
        "\nDecision rule: treat the earliest season where valid_rate and "
        "five_invariant are both stable & high (~>=0.97) as the real start of "
        "your usable range. Log it in STATUS.md.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
