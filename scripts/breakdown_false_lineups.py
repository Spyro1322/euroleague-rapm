#!/usr/bin/env python3
"""
Week-1 follow-up: characterise the validate_on_court_player == False residual
============================================================================

v2 — adds team-vs-named split. The Wk1 sweep showed valid_rate ~0.94-0.965; the
False residual concentrates in rebounds (O/D), turnovers and steals, while all
shooting/assist actions are ~0% false. That is the signature of TEAM rebounds /
TEAM turnovers — PBP rows with no individual attributed — not on-court players
misplaced into the wrong lineup.

This script confirms it by splitting every player-action False row into:
    team_event       PLAYER_ID is blank  -> no individual, benign, dropped by pbp_clean
    named_misattrib  PLAYER_ID present   -> a named player's action landed in a
                                            lineup without them = real error

The thesis number is the NAMED-misattribution rate: named_misattrib / all player
actions. If ~0, stint attribution is clean and you state it as fact in ch.3/ch.9.

Run:
    python scripts/breakdown_false_lineups.py --start 2007 --end 2025 \
        --games-per-season 5 --seed 42
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

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")
log = logging.getLogger("breakdown")
log.setLevel(logging.INFO)

# ---- PLAYTYPE classification (verified against 2007-2025 sample) ------------
# Structural / non-player rows: actor is a team or bench, "not in lineup" is
# expected and harmless.
BENIGN = {
    "BP", "EP", "EG",          # begin/end period, end game
    "TOUT", "TOUT_TV",         # timeouts
    "IN", "OUT",               # substitution markers themselves
    "JB", "TPOFF",             # jump ball / tip-off
    "CCH",                     # coach event
}
# Genuine individual actions: actor must be on court. A False with a NAMED player
# here is a real attribution error; a False with a blank PLAYER_ID is a team event.
PLAYER_ACTION = {
    "2FGM", "2FGA", "3FGM", "3FGA", "FTM", "FTA",   # shooting
    "DUNK", "LAYUPMD", "LAYUPATT", "2FGAB", "3FGAB",  # shooting (variant codes)
    "AS",                                            # assist (NB: code is AS, not AST)
    "O", "D",                                        # off/def rebound (incl. team rebs)
    "TO", "ST", "FV", "AG",                          # turnover, steal, block, blocked
    "CM", "CMU", "CMT", "RV", "OF",                  # fouls committed/received/offensive
}


def classify(pt: str) -> str:
    pt = (pt or "").strip()
    if pt in BENIGN:
        return "benign"
    if pt in PLAYER_ACTION:
        return "player_action"
    return "unclassified"


def is_blank(s: pd.Series) -> pd.Series:
    return s.isna() | (s.astype(str).str.strip().isin(["", "None", "nan"]))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=2007)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--games-per-season", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--competition", default="E", choices=["E", "U"])
    ap.add_argument("--out", type=Path,
                    default=Path("data/validation/wk1_false_breakdown.parquet"))
    args = ap.parse_args()

    random.seed(args.seed)
    pbp = PlayByPlay(competition=args.competition)
    sched = Schedule(competition=args.competition)

    keep = ["Season", "PLAYTYPE", "PLAYER_ID", "validate_on_court_player"]
    frames: list[pd.DataFrame] = []
    for season in range(args.start, args.end + 1):
        try:
            games = sched.get_gamecodes_season(season)
            played = games.loc[games.get("played", True) == True, "gameCode"].tolist()  # noqa: E712
            played = played or games["gameCode"].tolist()
        except Exception as exc:  # noqa: BLE001
            log.warning("season %s: schedule failed (%s)", season, exc)
            continue
        for gc in random.sample(played, min(args.games_per_season, len(played))):
            try:
                df = pbp.get_game_pbp_data_lineups(season=season, gamecode=int(gc),
                                                   validate=True)
            except Exception as exc:  # noqa: BLE001
                log.warning("season %s game %s failed (%s)", season, gc, exc)
                continue
            if df is None or df.empty or "validate_on_court_player" not in df:
                continue
            cols = [c for c in keep if c in df.columns]
            frames.append(df[cols].copy())
        log.info("season %s pulled", season)

    if not frames:
        print("No data pulled — check network access to live.euroleague.net.")
        return 1

    a = pd.concat(frames, ignore_index=True)
    a["PLAYTYPE"] = a["PLAYTYPE"].fillna("").str.strip()
    a["class"] = a["PLAYTYPE"].map(classify)
    a["is_false"] = ~a["validate_on_court_player"].astype(bool)
    a["blank_player"] = is_blank(a["PLAYER_ID"]) if "PLAYER_ID" in a else True
    # split False rows: team event (no individual) vs named mis-attribution
    a["false_team"] = a["is_false"] & a["blank_player"]
    a["false_named"] = a["is_false"] & ~a["blank_player"]

    # ---- per-PLAYTYPE table ------------------------------------------------
    by_pt = (
        a.groupby(["class", "PLAYTYPE"])
        .agg(n_total=("is_false", "size"),
             n_false=("is_false", "sum"),
             false_team=("false_team", "sum"),
             false_named=("false_named", "sum"))
        .reset_index()
    )
    by_pt["named_rate"] = (by_pt["false_named"] / by_pt["n_total"]).round(5)
    by_pt = by_pt.sort_values(["class", "n_false"], ascending=[True, False])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    by_pt.to_parquet(args.out, index=False)

    # ---- headline ----------------------------------------------------------
    pa = a[a["class"] == "player_action"]
    pa_n = len(pa)
    pa_false = int(pa["is_false"].sum())
    pa_team = int(pa["false_team"].sum())
    pa_named = int(pa["false_named"].sum())
    uncl = sorted(a.loc[a["class"] == "unclassified", "PLAYTYPE"].unique())

    pd.set_option("display.width", 130)
    print(f"\n=== False breakdown w/ team-vs-named split "
          f"({args.start}-{args.end}, {args.games_per_season} games/season) ===\n")
    print(by_pt.to_string(index=False))
    print("\n--- headline ---")
    print(f"total actions sampled            : {len(a):,}")
    print(f"player-action rows               : {pa_n:,}")
    print(f"  player-action False (any)      : {pa_false:,} ({pa_false/pa_n:.3%})")
    print(f"    -> team event (blank player) : {pa_team:,} ({pa_team/max(pa_false,1):.1%} of False) — benign")
    print(f"    -> NAMED mis-attribution     : {pa_named:,} ({pa_named/max(pa_false,1):.1%} of False)")
    print(f"\nNAMED-misattribution rate        : {pa_named/pa_n:.4%}  "
          f"({pa_named:,} of {pa_n:,})   <-- the thesis number")
    if uncl:
        print(f"\n[!] still UNCLASSIFIED (eyeball): {uncl}")
    else:
        print("\nAll PLAYTYPEs classified.")
    print(f"\nWritten: {args.out}")
    print(
        "\nRead: if team-event ~= 100% of player-action False and the "
        "named-misattribution rate is ~0, the residual is fully benign — "
        "rebounds/TOs/steals flagged False are team events, not real errors.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())