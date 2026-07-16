#!/usr/bin/env python3
"""
scripts/triage_id_collisions.py  —  Week 3, action 1b.

build_player_id_map.py flags name-strings owning >1 PLAYER_ID. Row counts alone
cannot tell you WHY. This script pulls season/team context for every colliding
(name, id) so each case can be resolved on evidence and documented in the thesis.

The discriminator:
  * IDs whose (season, team) footprints are DISJOINT and contiguous → almost
    certainly ONE player across an ID-scheme migration → MERGE.
  * IDs that co-occur in the same season, or sit on different teams at the same
    time → TWO players sharing a name → KEEP SEPARATE (merging would fuse two
    players into one ridge column).

Known ID schemes in this feed (2007-2026):
  legacy short   PKSF, PTHY, PLRU, AVD        (sometimes with/without 'P' prefix)
  team-scoped    MAD991, LJU1, PSIE374368     (team code + serial)
  modern canon   P000437, P012711, P005353
  junk           '1'

Outputs:
    reports/id_collision_triage.csv    one row per (name, id): seasons, teams, rows
    reports/id_merge_proposal.csv      auto-proposed merges (DISJOINT cases only)
                                       — REVIEW BY HAND before applying.

Run after build_player_id_map.py, before accepting stints_ids.parquet.
"""
from __future__ import annotations
import logging
import re
from pathlib import Path

import polars as pl

LOG = logging.getLogger("triage")

PBP_GLOB = "data/pbp_lineups/**/*.parquet"
BOX_GLOB = "landing/boxscore_players/**/*.parquet"
COLLISIONS = "reports/id_map_collisions.csv"
REPORTS = Path("reports")


def norm_id(s: str) -> str:
    """Normalise ONLY cosmetic scheme differences: optional leading 'P', then
    leading zeros. PAVD/AVD → AVD ; P001720/001720 → 1720."""
    if s is None:
        return ""
    s = str(s).strip().upper()
    s = re.sub(r"^P(?=\d)", "", s)      # P001720 -> 001720  (digits only)
    s = re.sub(r"^P(?=[A-Z]{2,})", "", s)  # PAVD -> AVD      (letter codes)
    s = re.sub(r"^0+", "", s)           # 001720 -> 1720
    return s


def pbp_context() -> pl.DataFrame:
    return (
        pl.scan_parquet(PBP_GLOB)
        .select(
            pl.col("PLAYER").cast(pl.Utf8).str.strip_chars().alias("name"),
            pl.col("PLAYER_ID").cast(pl.Utf8).str.strip_chars().alias("player_id"),
            pl.col("Season").cast(pl.Int64).alias("season"),
            pl.col("CODETEAM").cast(pl.Utf8).str.strip_chars().alias("team"),
        )
        .filter(pl.col("name").is_not_null() & (pl.col("name") != "")
                & pl.col("player_id").is_not_null() & (pl.col("player_id") != ""))
        .collect()
    )


def box_context() -> pl.DataFrame:
    try:
        return (
            pl.scan_parquet(BOX_GLOB)
            .select(
                pl.col("Player").cast(pl.Utf8).str.strip_chars().alias("name"),
                pl.col("Player_ID").cast(pl.Utf8).str.strip_chars().alias("player_id"),
                pl.col("Season").cast(pl.Int64).alias("season"),
                pl.col("Team").cast(pl.Utf8).str.strip_chars().alias("team"),
            )
            .filter(pl.col("name").is_not_null() & (pl.col("name") != "")
                    & pl.col("player_id").is_not_null()
                    & (pl.col("player_id") != ""))
            .collect()
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("no boxscore context (%s)", exc)
        return pl.DataFrame(schema={"name": pl.Utf8, "player_id": pl.Utf8,
                                    "season": pl.Int64, "team": pl.Utf8})


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    coll = pl.read_csv(COLLISIONS)
    names = coll["name"].unique().to_list()
    LOG.info("triaging %d colliding names", len(names))

    ctx = pl.concat([pbp_context(), box_context()], how="vertical_relaxed")
    ctx = ctx.filter(pl.col("name").is_in(names))

    per_id = (
        ctx.group_by("name", "player_id")
        .agg(
            pl.len().alias("n_rows"),
            pl.col("season").min().alias("season_min"),
            pl.col("season").max().alias("season_max"),
            pl.col("season").unique().sort().alias("seasons"),
            pl.col("team").unique().sort().alias("teams"),
        )
        .with_columns(pl.col("player_id").map_elements(norm_id, return_dtype=pl.Utf8)
                      .alias("id_norm"))
        .sort(["name", "n_rows"], descending=[False, True])
    )

    # ---- verdict per name -----------------------------------------------------
    verdicts = []
    for name in sorted(names):
        grp = per_id.filter(pl.col("name") == name)
        ids = grp["player_id"].to_list()
        norms = set(grp["id_norm"].to_list())
        season_sets = [set(s) for s in grp["seasons"].to_list()]
        team_sets = [set(t) for t in grp["teams"].to_list()]

        overlap = set()
        for i in range(len(season_sets)):
            for j in range(i + 1, len(season_sets)):
                overlap |= (season_sets[i] & season_sets[j])

        if len(norms) == 1:
            verdict, why = "MERGE_FORMAT", "ids identical once P-prefix/zeros normalised"
        elif not overlap:
            verdict, why = "MERGE_DISJOINT", "no shared season between ids (ID migration)"
        else:
            same_team = any(
                team_sets[i] & team_sets[j]
                for i in range(len(team_sets)) for j in range(i + 1, len(team_sets))
            )
            if same_team:
                verdict = "REVIEW_OVERLAP_SAMETEAM"
                why = f"shares season(s) {sorted(overlap)} AND team — likely same player, dup registration"
            else:
                verdict = "KEEP_SEPARATE_HOMONYM"
                why = f"shares season(s) {sorted(overlap)} on DIFFERENT teams — two players"
        verdicts.append({"name": name, "verdict": verdict, "reason": why,
                         "n_ids": len(ids), "ids": " | ".join(ids)})

    vdf = pl.DataFrame(verdicts)
    out = per_id.join(vdf.select("name", "verdict", "reason"), on="name", how="left")
    out = out.with_columns(
        pl.col("seasons").list.eval(pl.element().cast(pl.Utf8)).list.join(",")
        .alias("seasons"),
        pl.col("teams").list.join(",").alias("teams"),
    )
    REPORTS.mkdir(parents=True, exist_ok=True)
    out.write_csv(REPORTS / "id_collision_triage.csv")

    with pl.Config(tbl_rows=60, fmt_str_lengths=48, tbl_width_chars=200):
        LOG.info("triage:\n%s", out.select(
            "name", "player_id", "n_rows", "season_min", "season_max",
            "teams", "verdict"))
        LOG.info("verdict summary:\n%s", vdf.select("name", "verdict", "reason"))

    # ---- merge proposal: winner = most rows, for MERGE_* verdicts only ---------
    mergeable = vdf.filter(pl.col("verdict").str.starts_with("MERGE"))["name"].to_list()
    prop = []
    for name in mergeable:
        grp = per_id.filter(pl.col("name") == name).sort("n_rows", descending=True)
        winner = grp["player_id"][0]
        for loser in grp["player_id"].to_list()[1:]:
            prop.append({"name": name, "from_id": loser, "to_id": winner})
    pdf = pl.DataFrame(prop) if prop else pl.DataFrame(
        schema={"name": pl.Utf8, "from_id": pl.Utf8, "to_id": pl.Utf8})
    pdf.write_csv(REPORTS / "id_merge_proposal.csv")

    LOG.info("wrote reports/id_collision_triage.csv and reports/id_merge_proposal.csv")
    LOG.info("%d name(s) proposed for merge; %d flagged KEEP_SEPARATE / REVIEW",
             len(mergeable), len(names) - len(mergeable))
    LOG.warning("REVIEW id_merge_proposal.csv BY HAND before applying. A wrong "
                "merge fuses two players into one ridge column.")


if __name__ == "__main__":
    main()
