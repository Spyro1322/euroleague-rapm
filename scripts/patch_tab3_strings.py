#!/usr/bin/env python3
"""
patch_tab3_strings.py -- correct the figures in app/tab3_archetypes.py

Two defects, both found during the Unit 9 read-through:

1. THE MODULE DOCSTRING CARRIES A SUPERSEDED RUN.
   It reports Jaccard@10 = 0.147, per-K values 0.092/0.089/0.105, ARI +0.405,
   and a population of 362 reduced to 118. The deployed artifact and
   reports/tab3_format_decision.txt give 0.134, 0.094/0.083/0.096, +0.429, and
   379 reduced to 119. The rendered UI strings are already correct; only the
   comment is wrong -- but the comment is the first thing a reader of the
   repository sees, and Ch6 must not be cited from it.

2. THE JACCARD INDEX IS PRESENTED AS AN OVERLAP FRACTION.
   Both the docstring ("~85% turnover") and the st.info string ("agree only
   13%") treat 1 - J as the share of the list that changes. Jaccard is
   intersection over UNION, so for two lists of length K a value J corresponds
   to 2KJ/(1+J) shared members. At K=10, J=0.134 means about 2.4 of 10 shared,
   i.e. roughly three quarters turning over -- not 87%.

   The conclusion is unaffected: 2.4 of 10 on data that is four fifths identical
   is still a failure. The number was simply wrong.

   Note the K=1 case is exempt: for singleton sets the Jaccard index is 1 or 0,
   so its mean IS the proportion of players whose nearest neighbour is
   unchanged. 9.4% is correct as stated.

Idempotent: running twice is a no-op. Every replacement asserts its target
exists, so a drifted source fails loudly rather than silently doing nothing.

    python3 scripts/patch_tab3_strings.py [--path app/tab3_archetypes.py] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# (label, old, new)
EDITS: list[tuple[str, str, str]] = [
    (
        "docstring: neighbour-agreement figures",
        """  Neighbour-set agreement between the dash (2021-2025) and eval (2020-2024) fitting
  windows was Jaccard@10 = 0.147, and flat across K (0.092 at K=1, 0.089 at K=3,
  0.105 at K=5). Those two windows share FOUR OF FIVE SEASONS, so ~85% turnover in
  the neighbour list on ~80% shared data is a failure, not a marginal pass. Ranking
  individual players by similarity is not defensible on this data.""",
        """  Neighbour-set agreement between the dash (2021-2025) and eval (2020-2024)
  fitting windows was Jaccard@10 = 0.134 (0.094 at K=1, 0.083 at K=3, 0.096 at
  K=5). Jaccard is intersection over union, so 0.134 at K=10 is about 2.4 of ten
  neighbours in common -- roughly three quarters of the list turning over. Those
  two windows share FOUR OF FIVE SEASONS, so that is a failure on ~80% shared
  data, not a marginal pass. Agreement does not improve as the list is shortened:
  the single nearest neighbour is unchanged for only 9.4% of players. Ranking
  individual players by similarity is not defensible on this data.""",
    ),
    (
        "docstring: adjusted Rand index",
        """  Cluster membership over the same players survived: adjusted Rand index +0.405 at
  k=5, and stable across every k from 3 to 8 (+0.321 to +0.405). ARI is
  chance-corrected, so 0 is a random partition.""",
        """  Cluster membership over the same players survived: adjusted Rand index +0.429
  at k=5, and stable across every k from 3 to 7 (+0.315 to +0.429; k=8 is
  marginal at +0.253). ARI is chance-corrected, so 0 is a random partition.""",
    ),
    (
        "docstring: three-point exclusion population",
        """three-point contexts are excluded because Ch5 found them non-identifiable, and
including them collapses the reliably-placed population from 362 players to 118
while reordering neighbourhoods almost completely (Jaccard 0.102).""",
        """three-point contexts are excluded because Ch5 found them non-identifiable, and
including them collapses the reliably-placed population from 379 players to 119
while reordering neighbourhoods almost completely (Jaccard 0.102).""",
    ),
    (
        "st.info: neighbour-agreement wording",
        """f"that holds for every group count from 3 to 7, so k={k} is a presentational "
        f"choice rather than a tuned one. **Individual similarity is not stable** — "
        f"the ten nearest players to a given player agree only 13% between windows "
        f"that share four of five seasons. That is why this tab shows regions and "
        f"deliberately offers no 'most similar players' ranking.\"""",
        """f"that holds for every group count from 3 to 7, so k={k} is a presentational "
        f"choice rather than a tuned one. **Individual similarity is not stable** — "
        f"a ten-player 'most similar' list keeps only about two of its ten names "
        f"between windows that share four of five seasons, and the single closest "
        f"player changes for nine cases in ten. That is why this tab shows regions "
        f"and deliberately offers no 'most similar players' ranking.\"""",
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="app/tab3_archetypes.py")
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
        sys.exit(
            "\nOne or more targets were not found and nothing has been written.\n"
            "The source has drifted from the version this patch was written against.\n"
            "Apply those edits by hand rather than forcing this script."
        )

    if a.dry_run:
        print("\ndry run -- no changes written")
        return
    if src == original:
        print("\nno changes needed")
        return

    p.write_text(src)
    print(f"\nwritten: {p}")
    print("Verify the tab renders, then redeploy the mirror.")


if __name__ == "__main__":
    main()
