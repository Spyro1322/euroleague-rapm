"""
tag_shots.py — attach a play-context bucket + on-court 10 to every shot (O3 input)
==================================================================================
Tags every shot from the Points feed with one of the six buckets (play_context.py),
then joins to PBP on (Season, Gamecode, NUM_ANOT == NUMBEROFPLAY) to attach the
offensive and defensive fives. Output is the raw material for the Wk6 play-context
RAPM design matrix.

    python scripts/tag_shots.py --shots "data/shots/**/*.parquet" \
                                --pbp warehouse/pbp_poss.parquet \
                                --out warehouse/tagged_shots.parquet

DIAGNOSTICS (read these):
  • join-match-rate — % of shots that found their PBP row. If this isn't ~100%,
    the NUM_ANOT↔NUMBEROFPLAY key is wrong; fix before trusting anything downstream.
  • bucket distribution — sanity vs basketball priors (transition ~12-18%,
    second_chance ~8-12%, threes a big share in the modern game, etc.)
  • coord coverage — drives the corner/above-break split; low → those two collapse.
"""
from __future__ import annotations
import argparse
import polars as pl
from play_context import classify, THREE_ACTIONS, FG_ATTEMPTS

# ID_ACTION code → made-points (for the design matrix); misses = 0
MADE = {"2FGM": 2, "3FGM": 3, "LAYUPMD": 2, "DUNK": 2}


def tag(shots: pl.DataFrame, pbp: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    # --- keep only field-goal attempts; FTs and non-shot rows aren't tagged ----
    n_all = shots.height
    shots = shots.filter(pl.col("ID_ACTION").is_in(list(FG_ATTEMPTS)))
    n_fga = shots.height

    # --- classify each shot (row-wise; the logic is light) ----------------------
    def bucket_of(r) -> str:
        return classify(r["ID_ACTION"], bool(int(r["FASTBREAK"])),
                        bool(int(r["SECOND_CHANCE"])), r["COORD_X"], r["COORD_Y"])
    shots = shots.with_columns(
        pl.struct(["ID_ACTION", "FASTBREAK", "SECOND_CHANCE", "COORD_X", "COORD_Y"])
          .map_elements(bucket_of, return_dtype=pl.Utf8).alias("bucket"),
        pl.col("ID_ACTION").replace_strict(MADE, default=0, return_dtype=pl.Int32).alias("points"),
    )

    # --- join to PBP for the on-court 10 ---------------------------------------
    pbp_keyed = pbp.select(["Season", "Gamecode", "NUMBEROFPLAY", "PLAYER",
                            "Lineup_A", "Lineup_B"]).rename({"PLAYER": "pbp_player"})
    j = shots.join(
        pbp_keyed,
        left_on=["Season", "Gamecode", "NUM_ANOT"],
        right_on=["Season", "Gamecode", "NUMBEROFPLAY"],
        how="left",
    )
    matched = j.filter(pl.col("Lineup_A").is_not_null())

    # offence = the five containing the shooter; defence = the other
    def split_off(r):
        la, lb, shooter = r["Lineup_A"], r["Lineup_B"], r["PLAYER"]
        if la is not None and shooter in la:
            return {"off": la, "def": lb}
        return {"off": lb, "def": la}
    od = matched.with_columns(
        pl.struct(["Lineup_A", "Lineup_B", "PLAYER"]).map_elements(
            split_off, return_dtype=pl.Struct({"off": pl.List(pl.Utf8), "def": pl.List(pl.Utf8)})
        ).alias("od")
    ).with_columns(
        pl.col("od").struct.field("off").alias("off_players"),
        pl.col("od").struct.field("def").alias("def_players"),
    ).drop("od")

    out = od.select([
        "Season", "Gamecode", "NUM_ANOT", "TEAM", "PLAYER", "ID_ACTION",
        "bucket", "points", "FASTBREAK", "SECOND_CHANCE", "COORD_X", "COORD_Y",
        "off_players", "def_players",
    ])

    diag = {
        "shots": shots.height,
        "rows_all": n_all,
        "rows_fga": n_fga,
        "matched": matched.height,
        "match_rate": matched.height / shots.height if shots.height else 0.0,
        "buckets": out["bucket"].value_counts(sort=True),
        "threes_with_coords": (
            shots.filter(pl.col("ID_ACTION").is_in(list(THREE_ACTIONS)))
                 .select((pl.col("COORD_X").is_not_null() & (pl.col("COORD_X") != 0)).mean())
                 .item() if shots.height else 0.0
        ),
    }
    return out, diag


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="data/shots/**/*.parquet")
    ap.add_argument("--pbp", default="warehouse/pbp_poss.parquet")
    ap.add_argument("--out", default="warehouse/tagged_shots.parquet")
    a = ap.parse_args()

    shots = pl.read_parquet(a.shots)
    pbp = pl.read_parquet(a.pbp)
    out, d = tag(shots, pbp)
    out.write_parquet(a.out)

    print(f"{d['rows_all']:,} Points-feed rows → {d['rows_fga']:,} field-goal attempts "
          f"(dropped {d['rows_all']-d['rows_fga']:,} free throws / non-shots)")
    print(f"join-match-rate {d['match_rate']*100:.2f}% "
          f"(want ~100; low → NUM_ANOT↔NUMBEROFPLAY key wrong) → {a.out}")
    print(f"threes with coordinates: {d['threes_with_coords']*100:.1f}% "
          f"(drives corner/above-break split)")
    print("bucket distribution:")
    print(d["buckets"])


if __name__ == "__main__":
    main()