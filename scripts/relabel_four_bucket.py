"""
scripts/relabel_four_bucket.py

Applies the PINNED four-bucket location rules to any tagger output. No fitting,
no thresholds derived from the data being relabelled -- that is the whole point.
`derive_location_rules.py` was a one-off to recover the thresholds; this is the
reproducible step that belongs in the pipeline and in the weekly refresh.

RULES (centimetres; FIBA arc r = 675, corners 660)
    2-vs-3 from ID_ACTION       2FGA/2FGM  vs  3FGA/3FGM
    at_rim            <=>  2-pointer AND r < 200
    mid_range         <=>  2-pointer AND r >= 200
    corner_three      <=>  3-pointer AND |x| >= 660 AND y <= 225
    above_break_three <=>  3-pointer otherwise
    r = sqrt(x^2 + y^2), origin at the basket

The FASTBREAK / SECOND_CHANCE flags are IGNORED. They are populated on made
shots only (verified 2023: transition 1,954 rows with zero misses;
second_chance 2,741 with one), so they cannot support an efficiency rating; and
because the tagger applies precedence over location, their presence strips made
fastbreak/putback attempts out of the location buckets. Ignoring them fixes both.

REGRESSION CHECK
Where the input already carries location labels, this script reports agreement
with them. On 2023 that was 0.99792. A materially lower number on a new season
means either the coordinate system shifted or the tagger's own rules differ in
that era -- investigate before using the output.

Usage
    python3 scripts/relabel_four_bucket.py \
        --in warehouse/tagged_shots_ids.parquet \
        --out warehouse/tagged_shots_ids_4b.parquet
"""

import argparse
import json
from pathlib import Path

import polars as pl

# ---- PINNED. Do not fit these. Change only with a recorded reason.
AT_RIM_R = 200.0
CORNER_ABS_X = 660.0
CORNER_Y_MAX = 225.0
TWO_PT = ["2FGA", "2FGM"]
THREE_PT = ["3FGA", "3FGM"]
BUCKETS = ["at_rim", "mid_range", "corner_three", "above_break_three"]
LOCATION_LABELS = set(BUCKETS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default="warehouse/tagged_shots_ids.parquet")
    ap.add_argument("--out", dest="dst", default="warehouse/tagged_shots_ids_4b.parquet")
    ap.add_argument("--rules-out", default="reports/location_rules_pinned.json")
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    if not src.exists():
        raise SystemExit(f"input not found: {src}")

    df = pl.read_parquet(src)
    print(f"input: {src}  ({df.height:,} rows)")
    seasons = sorted(df["Season"].unique().to_list())
    print(f"seasons: {seasons[0]}-{seasons[-1]}  (n={len(seasons)})")
    if len(seasons) < 19:
        print(f"  NOTE: {19 - len(seasons)} season(s) absent. Missing: "
              f"{[s for s in range(2007, 2026) if s not in seasons]}")

    missing_cols = [c for c in ("COORD_X", "COORD_Y", "ID_ACTION") if c not in df.columns]
    if missing_cols:
        raise SystemExit(f"input lacks required columns: {missing_cols}")

    df = df.with_columns([
        pl.col("COORD_X").cast(pl.Float64).alias("_x"),
        pl.col("COORD_Y").cast(pl.Float64).alias("_y"),
    ]).with_columns((pl.col("_x") ** 2 + pl.col("_y") ** 2).sqrt().alias("_r"))

    # coordinate sanity: the arc should sit near 675
    three = df.filter(pl.col("ID_ACTION").is_in(THREE_PT))
    if three.height:
        p05 = three["_r"].quantile(0.05)
        print(f"3-point attempts: r p05={p05:.0f} (expect ~660-680 if units are cm)")
        if not (550 <= p05 <= 800):
            print("  !! r p05 is far from the expected arc distance. The coordinate")
            print("     system or unit may differ in this data. The pinned thresholds")
            print("     would then be wrong. STOP and check before using the output.")

    unknown_action = df.filter(~pl.col("ID_ACTION").is_in(TWO_PT + THREE_PT))
    if unknown_action.height:
        print(f"  !! {unknown_action.height:,} rows have an ID_ACTION outside "
              f"{TWO_PT + THREE_PT}:")
        print(unknown_action.group_by("ID_ACTION").agg(pl.len().alias("n"))
              .sort("n", descending=True).head(10))
        print("     These are classified by geometry alone (2-vs-3 falls back to the")
        print("     arc distance). Verify that is acceptable for those action codes.")

    is3 = (pl.col("ID_ACTION").is_in(THREE_PT)
           | (~pl.col("ID_ACTION").is_in(TWO_PT) & (pl.col("_r") >= 675.0)))
    is_corner = (pl.col("_x").abs() >= CORNER_ABS_X) & (pl.col("_y") <= CORNER_Y_MAX)

    new_bucket = (
        pl.when(is3 & is_corner).then(pl.lit("corner_three"))
         .when(is3).then(pl.lit("above_break_three"))
         .when(pl.col("_r") < AT_RIM_R).then(pl.lit("at_rim"))
         .otherwise(pl.lit("mid_range"))
    )

    had_bucket = "bucket" in df.columns
    out = df.with_columns(new_bucket.alias("_new"))

    if had_bucket:
        located = out.filter(pl.col("bucket").is_in(list(LOCATION_LABELS)))
        if located.height:
            agree = located.filter(pl.col("bucket") == pl.col("_new")).height
            rate = agree / located.height
            print(f"\nregression check vs existing location labels: "
                  f"{agree:,}/{located.height:,} = {rate:.5f}")
            if rate < 0.99:
                print("  !! BELOW 0.99. The pinned rules disagree with this tagger")
                print("     output more than expected. Either the coordinate system")
                print("     changed or the tagger's rules differ here. Investigate.")
            per_season = (located.with_columns(
                (pl.col("bucket") == pl.col("_new")).alias("ok"))
                .group_by("Season").agg([
                    pl.len().alias("n"), pl.col("ok").mean().alias("agree")
                ]).sort("Season"))
            print(per_season)
            worst = per_season.filter(pl.col("agree") < 0.98)
            if worst.height:
                print(f"  !! season(s) below 0.98 agreement — these need attention:")
                print(worst)

        moved = out.filter(~pl.col("bucket").is_in(list(LOCATION_LABELS)))
        if moved.height:
            print(f"\nreclassified {moved.height:,} previously situation-labelled rows:")
            print(moved.group_by(["bucket", "_new"]).agg(pl.len().alias("n"))
                  .sort(["bucket", "n"], descending=[False, True]))

        out = out.drop("bucket")

    out = out.rename({"_new": "bucket"}).drop(["_x", "_y", "_r"])

    print("\nfinal bucket distribution:")
    dist = out.group_by("bucket").agg([
        pl.len().alias("attempts"),
        (pl.col("points") > 0).sum().alias("made"),
        pl.col("points").sum().alias("pts"),
    ]).with_columns([
        (pl.col("made") / pl.col("attempts")).round(4).alias("fg_pct"),
        (100 * pl.col("pts") / pl.col("attempts")).round(2).alias("pts_per_100"),
    ]).sort("attempts", descending=True)
    print(dist)
    print("\n  expected: at_rim ~0.65, above_break ~0.35, corner ~0.44, mid ~0.40")
    print("  pts/100 ordering: corner ~= at_rim > above_break > mid_range")

    dst.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(dst)
    print(f"\nwrote {dst}  ({out.height:,} rows)")

    rules = dict(at_rim_radius=AT_RIM_R, corner_abs_x_min=CORNER_ABS_X,
                 corner_y_max=CORNER_Y_MAX, two_pt_codes=TWO_PT,
                 three_pt_codes=THREE_PT, buckets=BUCKETS, pinned=True,
                 units="centimetres", fiba_arc_r=675, fiba_corner_r=660,
                 situation_flags="ignored (populated on made shots only)")
    rp = Path(args.rules_out)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(rules, indent=2))
    print(f"wrote {rp}")


if __name__ == "__main__":
    main()
