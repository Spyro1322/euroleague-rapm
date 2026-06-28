"""
validate_tagging.py — the 20×5 manual check + coordinate calibration
====================================================================
Samples 20 shots from each of 5 games, classifies them, and writes a flat CSV you
eyeball against the official Euroleague shot chart / PBP. Also prints the
three-point and two-point coordinate distributions so the PROVISIONAL thresholds
in play_context.py (CORNER_*, RIM_RADIUS, SIDELINE_AXIS) get calibrated against
real data rather than guessed.

    python scripts/validate_tagging.py --shots "data/shots/season=2023/*.parquet" \
                                       --out docs/tagging_validation_2023.csv --seed 42

WHAT TO CHECK in the CSV (per row): does `bucket` match what the shot actually was?
  • transition/second_chance — trust the feed flags
  • at_rim vs mid_range — is the 2FG split sensible?
  • corner vs above_break — THIS is the one to scrutinize; if the coord scatter
    printed below doesn't cleanly separate, set play_context to a single 'three'
    bucket (→ five buckets) per the Wk2 fallback.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import polars as pl
from play_context import classify, THREE_ACTIONS, TWO_ACTIONS, RIM_ACTIONS


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="data/shots/season=2023/*.parquet")
    ap.add_argument("--out", default="docs/tagging_validation.csv")
    ap.add_argument("--games", type=int, default=5)
    ap.add_argument("--per_game", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    df = pl.read_parquet(a.shots)

    # ── coordinate distributions — the calibration evidence ────────────────────
    threes = df.filter(pl.col("ID_ACTION").is_in(list(THREE_ACTIONS)))
    twos = df.filter(pl.col("ID_ACTION").is_in(list(TWO_ACTIONS) + list(RIM_ACTIONS)))
    qs = [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0]
    print("THREE-POINT coords (calibrate CORNER_* + SIDELINE_AXIS):")
    print(threes.select(
        [pl.col("COORD_X").quantile(q).alias(f"X_{int(q*100)}") for q in qs] +
        [pl.col("COORD_Y").quantile(q).alias(f"Y_{int(q*100)}") for q in qs]))
    print("dist-from-basket sqrt(x^2+y^2) for twos vs threes (verify 675 arc, RIM_RADIUS):")
    print(df.with_columns(
        (pl.col("COORD_X").pow(2) + pl.col("COORD_Y").pow(2)).sqrt().alias("dist"),
        pl.when(pl.col("ID_ACTION").is_in(list(THREE_ACTIONS))).then(pl.lit("three"))
          .otherwise(pl.lit("two")).alias("kind"),
    ).group_by("kind").agg(
        pl.col("dist").min().alias("min"), pl.col("dist").median().alias("med"),
        pl.col("dist").max().alias("max")))

    # ── 20×5 sample for manual eyeballing ──────────────────────────────────────
    game_ids = (df.select(["Season", "Gamecode"]).unique()
                  .sample(a.games, seed=a.seed))
    sample = (df.join(game_ids, on=["Season", "Gamecode"], how="inner")
                .group_by(["Season", "Gamecode"], maintain_order=True)
                .map_groups(lambda g: g.sample(min(a.per_game, g.height), seed=a.seed)))

    sample = sample.with_columns(
        pl.struct(["ID_ACTION", "FASTBREAK", "SECOND_CHANCE", "COORD_X", "COORD_Y"])
          .map_elements(lambda r: classify(r["ID_ACTION"], bool(int(r["FASTBREAK"])),
                                           bool(int(r["SECOND_CHANCE"])),
                                           r["COORD_X"], r["COORD_Y"]),
                        return_dtype=pl.Utf8).alias("bucket")
    ).select(["Season", "Gamecode", "NUM_ANOT", "TEAM", "PLAYER", "ACTION",
              "ID_ACTION", "POINTS", "FASTBREAK", "SECOND_CHANCE",
              "COORD_X", "COORD_Y", "ZONE", "bucket"]).sort(["Gamecode", "NUM_ANOT"])

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sample.write_csv(a.out)
    print(f"\n{sample.height} shots ({a.games}×{a.per_game}) → {a.out}")
    print("bucket mix in sample:")
    print(sample["bucket"].value_counts(sort=True))


if __name__ == "__main__":
    main()
