#!/usr/bin/env python3
"""
scripts/build_player_id_map.py  —  Week 3, action 1 (the blocker).  VERSION 2.

Remaps lineups in stints.parquet (and tagged_shots) from NAME STRINGS to
canonical PLAYER_IDs.

WHY THE KEY IS (name, season) AND NOT name
-------------------------------------------
v1 keyed on the name string alone and resolved ties by "most rows wins". Triage
(reports/id_collision_triage.csv) found 10 colliding names. Nine are one player
under two ids (format artifacts, legacy team-scoped ids, a typo, a junk id '1',
one duplicate registration) — those are merged via config/id_merges.csv.

The tenth, SIMONOVIC, MARKO, is TWO DIFFERENT PLAYERS (b.1986 Serbian SF, id
PLRU; b.1999 Montenegrin C, id P012711 — verified against EuroLeague official
profiles). Under a name-keyed map the 1999 player's rows would be silently
credited to the 1986 player. Keying on (name, season) separates them cleanly:
their careers do not overlap in time. It also protects the O5 weekly refresh,
where a new homonym could appear in any future season.

INVARIANT (hard-enforced): after merges, every (name, season) resolves to exactly
ONE player_id. If not, the script exits non-zero — it never guesses.

Outputs:
    warehouse/player_id_map.parquet      name, season → player_id
    warehouse/stints_ids.parquet         lineups as ID lists
    warehouse/tagged_shots_ids.parquet   shots with player_id + ID lists
    reports/id_map_unresolved.csv        (name, season) with >1 id  — must be empty
    reports/id_map_unmapped.csv          lineup (name, season) with no id

Run: after ingest_boxscore.py + triage, before build_rapm_design.py.
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path

import polars as pl

LOG = logging.getLogger("id_map")

# ============================================================ CONFIG (verified)
PBP_GLOB = "data/pbp_lineups/**/*.parquet"
BOX_GLOB = "landing/boxscore_players/**/*.parquet"
MERGES = "config/id_merges.csv"          # curated, hand-verified

STINTS_IN = "warehouse/stints.parquet"
STINTS_OUT = "warehouse/stints_ids.parquet"
SEASON_COL = "Season"
HOME_LINEUP_COL = "home_players"
AWAY_LINEUP_COL = "away_players"

SHOTS_IN = "warehouse/tagged_shots.parquet"
SHOTS_OUT = "warehouse/tagged_shots_ids.parquet"
SHOTS_NAME_COL = "PLAYER"
SHOTS_LIST_COLS = ["off_players", "def_players"]

REPORTS = Path("reports")
# =============================================================================


def load_merges() -> dict[str, str]:
    p = Path(MERGES)
    if not p.exists():
        LOG.warning("%s not found — NO merges applied. Collisions will remain.", p)
        return {}
    df = pl.read_csv(p, comment_prefix="#")
    m = dict(zip(df["from_id"].cast(pl.Utf8).to_list(),
                 df["to_id"].cast(pl.Utf8).to_list()))
    LOG.info("loaded %d curated id merges from %s", len(m), p)
    return m


def pbp_pairs() -> pl.DataFrame:
    return (
        pl.scan_parquet(PBP_GLOB)
        .select(
            pl.col("PLAYER").cast(pl.Utf8).str.strip_chars().alias("name"),
            pl.col("PLAYER_ID").cast(pl.Utf8).str.strip_chars().alias("player_id"),
            pl.col("Season").cast(pl.Int64).alias("season"),
        )
        .filter(pl.col("name").is_not_null() & (pl.col("name") != "")
                & pl.col("player_id").is_not_null() & (pl.col("player_id") != ""))
        .group_by("name", "season", "player_id").len().rename({"len": "n_rows"})
        .collect()
        .with_columns(pl.lit("pbp").alias("source"))
    )


def box_pairs() -> pl.DataFrame:
    empty = pl.DataFrame(schema={"name": pl.Utf8, "season": pl.Int64,
                                 "player_id": pl.Utf8, "n_rows": pl.UInt32,
                                 "source": pl.Utf8})
    try:
        return (
            pl.scan_parquet(BOX_GLOB)
            .select(
                pl.col("Player").cast(pl.Utf8).str.strip_chars().alias("name"),
                pl.col("Player_ID").cast(pl.Utf8).str.strip_chars().alias("player_id"),
                pl.col("Season").cast(pl.Int64).alias("season"),
            )
            .filter(pl.col("name").is_not_null() & (pl.col("name") != "")
                    & pl.col("player_id").is_not_null() & (pl.col("player_id") != ""))
            .group_by("name", "season", "player_id").len().rename({"len": "n_rows"})
            .collect()
            .with_columns(pl.lit("box").alias("source"))
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("no boxscore backstop (%s)", exc)
        return empty


def build_map() -> pl.DataFrame:
    merges = load_merges()
    pbp = pbp_pairs()
    box = box_pairs()
    LOG.info("PBP: %d (name,season,id) rows | boxscore: %d", pbp.height, box.height)

    # boxscore only fills (name, season) the PBP never saw
    box_extra = box.join(pbp.select("name", "season"), on=["name", "season"],
                         how="anti")
    LOG.info("boxscore adds %d (name,season) combos unseen in PBP", box_extra.height)
    both = pl.concat([pbp, box_extra], how="vertical_relaxed")

    # apply curated merges
    if merges:
        both = both.with_columns(
            pl.col("player_id").replace(merges).alias("player_id")
        )
        both = (both.group_by("name", "season", "player_id")
                .agg(pl.col("n_rows").sum(),
                     pl.col("source").min().alias("source")))

    # ---- INVARIANT: one id per (name, season) --------------------------------
    dupes = (
        both.group_by("name", "season")
        .agg(pl.col("player_id").n_unique().alias("n_ids"),
             pl.col("player_id").unique().sort().str.join(" | ").alias("ids"))
        .filter(pl.col("n_ids") > 1)
        .sort(["name", "season"])
    )
    REPORTS.mkdir(parents=True, exist_ok=True)
    if dupes.height:
        dupes.write_csv(REPORTS / "id_map_unresolved.csv")
        with pl.Config(tbl_rows=40, fmt_str_lengths=60):
            LOG.error("UNRESOLVED — %d (name, season) combos still map to >1 id:\n%s",
                      dupes.height, dupes)
        LOG.error("Add the missing merges to %s (or confirm a same-season homonym, "
                  "which needs a team-aware key). Refusing to guess. See "
                  "reports/id_map_unresolved.csv", MERGES)
        sys.exit(3)
    LOG.info("invariant holds: every (name, season) → exactly one id ✔")

    canon = (both.sort("n_rows", descending=True)
             .group_by("name", "season").first()
             .select("name", "season", "player_id", "n_rows", "source"))
    Path("warehouse").mkdir(parents=True, exist_ok=True)
    canon.write_parquet("warehouse/player_id_map.parquet")
    LOG.info("wrote warehouse/player_id_map.parquet (%d name-season rows, "
             "%d distinct players)", canon.height, canon["player_id"].n_unique())
    return canon


def _remap_list_col(df: pl.DataFrame, col: str, canon: pl.DataFrame) -> pl.DataFrame:
    """Season-aware remap of a list[str] of names → list[str] of ids, order kept."""
    long = (
        df.select("_row", SEASON_COL, col)
        .explode(col)
        .with_columns(pl.int_range(pl.len()).over("_row").alias("_pos"))
        .join(canon.select("name", "season", "player_id"),
              left_on=[col, SEASON_COL], right_on=["name", "season"], how="left")
        .sort(["_row", "_pos"])
    )
    agg = (long.group_by("_row", maintain_order=True)
           .agg(pl.col("player_id").alias(col)))
    return df.drop(col).join(agg, on="_row", how="left")


def remap_stints(canon: pl.DataFrame) -> None:
    df = pl.read_parquet(STINTS_IN).with_row_index("_row")
    for c in (SEASON_COL, HOME_LINEUP_COL, AWAY_LINEUP_COL):
        if c not in df.columns:
            LOG.error("stints missing %r. Columns: %s", c, df.columns)
            sys.exit(2)

    # audit unmapped BEFORE remap
    names_long = pl.concat([
        df.select(pl.col(HOME_LINEUP_COL).alias("name"), pl.col(SEASON_COL)),
        df.select(pl.col(AWAY_LINEUP_COL).alias("name"), pl.col(SEASON_COL)),
    ]).explode("name").drop_nulls().unique()
    unmapped = names_long.join(canon.select("name", "season"),
                               left_on=["name", SEASON_COL],
                               right_on=["name", "season"], how="anti")
    if unmapped.height:
        unmapped.write_csv(REPORTS / "id_map_unmapped.csv")
        LOG.error("%d (name, season) lineup combos have NO id — see reports/"
                  "id_map_unmapped.csv", unmapped.height)
    else:
        LOG.info("all lineup (name, season) combos mapped ✔")

    out = _remap_list_col(df, HOME_LINEUP_COL, canon)
    out = _remap_list_col(out, AWAY_LINEUP_COL, canon)
    out = out.drop("_row")
    out.write_parquet(STINTS_OUT)
    LOG.info("wrote %s (%d stints)", STINTS_OUT, out.height)


def remap_shots(canon: pl.DataFrame) -> None:
    # ---- CHANGED: was a try/except that warned and returned ------------------
    p = Path(SHOTS_IN)
    if not p.exists():
        LOG.error("no tagged shots at %s — run tag_shots.py first. Refusing to "
                  "continue silently.", SHOTS_IN)
        sys.exit(4)
    df = pl.read_parquet(p).with_row_index("_row")

    seasons = sorted(df["Season"].unique().to_list())
    LOG.info("tagged shots span %d season(s): %d-%d", len(seasons),
             seasons[0], seasons[-1])
    if len(seasons) < 19:
        LOG.warning("only %d/19 seasons present. Missing: %s", len(seasons),
                    [s for s in range(2007, 2026) if s not in seasons])
    # ---- end change ----------------------------------------------------------

    if SHOTS_NAME_COL not in df.columns or SEASON_COL not in df.columns:
        LOG.error("tagged_shots lacks %r/%r — cannot remap shooters.",
                  SHOTS_NAME_COL, SEASON_COL)
        sys.exit(5)

    out = df.join(canon.select("name", "season", "player_id"),
                  left_on=[SHOTS_NAME_COL, SEASON_COL],
                  right_on=["name", "season"], how="left")
    n_null = out["player_id"].null_count()
    LOG.info("shooters: %d/%d unmapped (%.2f%%)", n_null, out.height,
             100.0 * n_null / max(out.height, 1))

    for c in SHOTS_LIST_COLS:
        if c in out.columns:
            out = _remap_list_col(out, c, canon)
    out = out.drop("_row")
    out.write_parquet(SHOTS_OUT)
    LOG.info("wrote %s", SHOTS_OUT)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    canon = build_map()
    remap_stints(canon)
    remap_shots(canon)
    LOG.info("done → run build_rapm_design.py")


if __name__ == "__main__":
    main()