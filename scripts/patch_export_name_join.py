#!/usr/bin/env python3
"""
patch_export_name_join.py -- fix the name join in export_shotctx_parquet.py

THE BUG
`name` is joined from the leaderboard artifact, which is FLOORED FOR DISPLAY.
Every player below that floor therefore exports with a null name -- 184 of them
in the dash window (701 rated in the shot-context fit, 517 on the leaderboard).
An identity field is being supplied by a presentation setting.

It is benign on the dashboard, which simply cannot offer those players in its
selector, but it is wrong at source: `player_id_map.parquet` is the authority on
identity and carries 2,374 players. Anything downstream that reads the exported
parquet and expects `name` to be populated inherits the defect.

THE FIX
Take `name` from the id map and keep `poss` / `ORAPM` / `DRAPM` from the
leaderboard, which is where they belong. The id map is (name, season)-keyed, so
the most recent season's spelling is taken -- consistent with the rest of the
pipeline.

The sign assertions are unaffected: they compare `prior` against ORAPM/DRAPM
only where those are non-null, and both still come from the leaderboard.

DIAGNOSTIC SPLIT
The existing message conflates two different conditions under "unnamed". After
this patch they are reported separately, matching the script's own practice of
carrying distinct suppression reasons distinctly:
  - no name in the id map      -> a genuine identity failure, warn loudly
  - no poss on the leaderboard -> below the display floor, expected and benign

ALSO REMOVED
The docstring's claim that three-point outcomes are "a known plus-minus result"
is unsourced. It appears in no report, and Ch5 §5.8 and Ch9 §9.2 now argue the
point from Franks et al. (2015) instead -- defenders influence where shots are
taken more than whether they fall, and this model conditions on location, so it
is estimated on the weaker channel.

    python3 scripts/patch_export_name_join.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

EDITS: list[tuple[str, str, str]] = [
    (
        "load the id map alongside the leaderboard",
        """    lb_small = lb.select(["player_id", "name", "poss", "ORAPM", "DRAPM"])""",
        """    lb_small = lb.select(["player_id", "poss", "ORAPM", "DRAPM"])

    # NAME COMES FROM THE ID MAP, NOT THE LEADERBOARD.
    # The leaderboard is floored for display, so joining names from it left every
    # player below that floor with a null name -- an identity field supplied by a
    # presentation setting. player_id_map.parquet is the authority on identity.
    # It is (name, season)-keyed, so take the most recent season's spelling.
    idmap = (pl.read_parquet(W / "player_id_map.parquet")
               .sort("season", descending=True)
               .unique(subset=["player_id"], keep="first")
               .select(["player_id", "name"]))
    print(f"  id map: player_id_map.parquet ({idmap.height} players)")""",
    ),
    (
        "join name from the id map, exposure from the leaderboard",
        """    ).join(lb_small, on="player_id", how="left")""",
        """    ).join(idmap, on="player_id", how="left"
    ).join(lb_small, on="player_id", how="left")""",
    ),
    (
        "report identity failure and display floor separately",
        """    unnamed = df.filter(pl.col("name").is_null())["player_id"].n_unique()
    if unnamed:
        print(f"  {unnamed} player(s) absent from the leaderboard (below its display "
              f"floor); they carry prior 0 and are not selectable in the dashboard.")""",
        """    unnamed = df.filter(pl.col("name").is_null())["player_id"].n_unique()
    if unnamed:
        print(f"  WARNING: {unnamed} player(s) have no name in player_id_map.parquet.")
        print(f"  That is an identity failure, not a display floor. Two ids schemes")
        print(f"  coexist (P\\\\d{{6}} and legacy P[A-Z]{{3}}); check the map covers both")
        print(f"  before shipping this artifact.")
    unlisted = df.filter(pl.col("poss").is_null())["player_id"].n_unique()
    if unlisted:
        print(f"  {unlisted} player(s) sit below the leaderboard's display floor and "
              f"carry no overall possession count. They are named and exported; only "
              f"the exposure column is absent.")""",
    ),
    (
        "docstring: name provenance",
        """    player_id, name, poss   identity + overall exposure""",
        """    player_id, name         identity, from player_id_map.parquet (NOT the
                            leaderboard, which is floored for display)
    poss                    overall exposure, from the leaderboard; null for
                            players below its display floor""",
    ),
    (
        "docstring: drop the unsourced repeatability claim",
        """Two-point buckets measure shot creation and rim protection, which are repeatable
on-court skills. Three-point buckets measure three-point outcomes, which largely
are not repeatable at lineup level -- a known plus-minus result, reproduced here.""",
        """Two-point buckets measure shot creation and rim protection, which are repeatable
on-court skills. The three-point result is what the spatial-defence literature
predicts: Franks et al. (2015) find a defender's influence falls mainly on where
opponents shoot from rather than on whether those shots fall, and this model
conditions on location, so it is estimated on the weaker channel. See Ch5 s5.8.""",
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="scripts/export_shotctx_parquet.py")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = Path(a.path)
    if not p.exists():
        sys.exit(f"not found: {p}")
    src = original = p.read_text()

    applied, skipped, missing = [], [], []
    for label, old, new in EDITS:
        if new in src:
            skipped.append(label)
        elif old in src:
            src = src.replace(old, new, 1)
            applied.append(label)
        else:
            missing.append(label)

    for label in applied:
        print(f"  applied : {label}")
    for label in skipped:
        print(f"  already : {label}")
    for label in missing:
        print(f"  MISSING : {label}")

    if missing:
        sys.exit("\nTarget(s) not found; nothing written. Apply by hand.")
    if a.dry_run:
        print("\ndry run -- no changes written")
        return
    if src == original:
        print("\nno changes needed")
        return

    p.write_text(src)
    print(f"\nwritten: {p}")
    print("\nRe-export all three windows, then redeploy:")
    print("  for w in baseline dash eval; do "
          "python3 scripts/export_shotctx_parquet.py --window $w; done")
    print("Expect the unnamed count to fall to 0 and a new line reporting the")
    print("players below the leaderboard display floor.")


if __name__ == "__main__":
    main()
