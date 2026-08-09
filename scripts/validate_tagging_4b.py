#!/usr/bin/env python3
"""
validate_tagging_4b.py -- exhaustive validation of the FOUR-context taxonomy
============================================================================
Replaces `validate_tagging.py`, which is unusable against the current pipeline:
it recomputes `bucket` via play_context.classify() (the superseded six-bucket,
flag-precedence function), reads raw data/shots/ rather than the warehouse, and
selects columns (ACTION, POINTS, ZONE) absent from the shipped schema.

This script validates the SHIPPED artifact, exhaustively, across all seasons.
Sampling is the wrong instrument for the open risk: the pre-2015 action-code
vocabulary gap is a population property. A 100-shot eyeball can contain zero
instances of a code appearing in 0.5% of rows; a full pass cannot miss it.

WHAT IT ANSWERS
  1. Are the stored buckets reproducible from the pinned rules? (agreement 1.000
     or a localised disagreement set)
  2. WHICH pinned rules actually ran? corner depth 220 vs 225, rim radius < vs
     <=, RIM_ACTIONS always-at_rim vs coordinate-subject. Four combinations are
     scored; the one reaching 1.000 is the rule that produced the artifact.
  3. What is the action-code vocabulary by season, and how does each code route?
     (closes the Ch5 s5.2.5 open item)
  4. Where does coordinate orientation fail, by season? (quantifies the 2013-14
     concentration for Ch9 s9.1)

WHAT IT DOES NOT DO
  No re-derivation is a substitute for eyes on a shot chart: a systematically
  mis-oriented coordinate frame is internally consistent and will reproduce
  perfectly. --sample writes a small manual-check CSV carrying the STORED
  bucket, as corroborating appendix evidence.

USAGE
    python3 scripts/validate_tagging_4b.py \
        --shots warehouse/tagged_shots.parquet \
        --outdir reports --sample 40 --sample-seasons 2013 2014
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------- action codes
RIM_ACTIONS = {"LAYUPMD", "LAYUPATT", "DUNK"}
TWO_ACTIONS = {"2FGM", "2FGA", "2FGAB"}
THREE_ACTIONS = {"3FGM", "3FGA", "3FGAB"}
FG_ATTEMPTS = RIM_ACTIONS | TWO_ACTIONS | THREE_ACTIONS

# ------------------------------------------------- pinned geometry (cm)
ARC = 675.0
RIM_RADIUS = 200.0
CORNER_SIDELINE_MIN = 660.0
# CORNER_DEPTH is disputed across sources (220 in play_context.py and STATUS.md,
# 225 in relabel_four_bucket.py). Both are scored below; do not hard-code a
# winner into the appendix until this script names one.
CORNER_DEPTH_CANDIDATES = (220.0, 225.0)

BUCKETS = ("at_rim", "mid_range", "corner_three", "above_break_three")


def _radius() -> pl.Expr:
    return (
        pl.col("COORD_X").cast(pl.Float64).pow(2)
        + pl.col("COORD_Y").cast(pl.Float64).pow(2)
    ).sqrt()


def derive_bucket(corner_depth: float, rim_strict: bool, rim_always: bool) -> pl.Expr:
    """Independent re-derivation of the four-context label from raw fields.

    corner_depth : COORD_Y ceiling for a corner three
    rim_strict   : True -> at_rim iff r <  RIM_RADIUS  (relabel_four_bucket)
                   False-> at_rim iff r <= RIM_RADIUS  (play_context)
    rim_always   : True -> RIM_ACTIONS are at_rim regardless of coordinates
    """
    r = _radius()
    is_three = pl.col("ID_ACTION").is_in(sorted(THREE_ACTIONS))
    is_rim_action = pl.col("ID_ACTION").is_in(sorted(RIM_ACTIONS))
    is_two = pl.col("ID_ACTION").is_in(sorted(TWO_ACTIONS)) | is_rim_action

    is_corner = (pl.col("COORD_X").abs() >= CORNER_SIDELINE_MIN) & (
        pl.col("COORD_Y") <= corner_depth
    )
    three_b = (
        pl.when(is_corner)
        .then(pl.lit("corner_three"))
        .otherwise(pl.lit("above_break_three"))
    )

    near = (r < RIM_RADIUS) if rim_strict else (r <= RIM_RADIUS)
    two_b = pl.when(near).then(pl.lit("at_rim")).otherwise(pl.lit("mid_range"))
    if rim_always:
        two_b = pl.when(is_rim_action).then(pl.lit("at_rim")).otherwise(two_b)

    return (
        pl.when(is_three)
        .then(three_b)
        .when(is_two)
        .then(two_b)
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias("derived")
    )


def flag_expr(col: str) -> pl.Expr:
    """FASTBREAK / SECOND_CHANCE arrive as int, bool or str depending on vintage."""
    return pl.col(col).cast(pl.Utf8, strict=False).is_in(["1", "true", "True"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="warehouse/tagged_shots.parquet")
    ap.add_argument("--outdir", default="reports")
    ap.add_argument("--sample", type=int, default=0,
                    help="rows per season for the manual-check CSV (0 = skip)")
    ap.add_argument("--sample-seasons", type=int, nargs="*", default=[2013, 2014])
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    df = pl.read_parquet(a.shots)
    report: dict = {"source": a.shots, "rows": df.height}

    print("=" * 78)
    print(f"TAGGING VALIDATION (four-context) -- {a.shots}")
    print("=" * 78)
    print(f"rows: {df.height:,}")

    seasons = sorted(df["Season"].unique().to_list())
    report["seasons"] = seasons
    print(f"seasons: {len(seasons)} ({seasons[0]}-{seasons[-1]})")

    stored_mix = df.group_by("bucket").len().sort("len", descending=True)
    print("\nstored bucket mix:")
    print(stored_mix)
    report["stored_mix"] = {r["bucket"]: r["len"] for r in stored_mix.to_dicts()}

    unexpected = [b for b in report["stored_mix"] if b not in BUCKETS]
    if unexpected:
        print(f"\n!! STORED BUCKETS OUTSIDE THE FOUR-CONTEXT TAXONOMY: {unexpected}")
    report["unexpected_buckets"] = unexpected

    # -- 1. which pinned rule set reproduces the artifact? --------------------
    print("\n" + "-" * 78)
    print("1. RULE RECOVERY -- which pinned constants produced the stored column?")
    print("-" * 78)
    combos, best = [], None
    for depth in CORNER_DEPTH_CANDIDATES:
        for rim_strict in (True, False):
            for rim_always in (True, False):
                d = df.with_columns(derive_bucket(depth, rim_strict, rim_always))
                n_ok = d.filter(
                    pl.col("bucket").eq_missing(pl.col("derived"))
                ).height
                rate = n_ok / df.height if df.height else 0.0
                row = {
                    "corner_depth": depth,
                    "rim_strict_lt": rim_strict,
                    "rim_actions_always_at_rim": rim_always,
                    "agreement": rate,
                    "disagreements": df.height - n_ok,
                }
                combos.append(row)
                if best is None or rate > best["agreement"]:
                    best = row
    combos.sort(key=lambda c: -c["agreement"])
    for c in combos:
        print(f"  depth={c['corner_depth']:.0f}  rim_lt={c['rim_strict_lt']!s:<5}  "
              f"rim_always={c['rim_actions_always_at_rim']!s:<5}  "
              f"agreement={c['agreement']:.6f}  ({c['disagreements']:,} disagree)")
    report["rule_recovery"] = combos
    report["rule_recovered"] = best
    ties = [c for c in combos if c["agreement"] == best["agreement"]]
    report["rule_recovery_ties"] = len(ties)
    if best["agreement"] == 1.0:
        def _axis(key, fmt):
            vals = {fmt(c[key]) for c in ties}
            return next(iter(vals)) if len(vals) == 1 else "UNDETERMINED " + "/".join(sorted(vals))
        print(f"\n  -> EXACT ({len(ties)} rule set(s) reproduce the artifact):")
        print(f"     corner depth      : {_axis('corner_depth', lambda v: f'{v:.0f}')}")
        print(f"     rim radius test   : {_axis('rim_strict_lt', lambda v: '< 200' if v else '<= 200')}")
        print(f"     RIM_ACTIONS       : {_axis('rim_actions_always_at_rim', lambda v: 'always at_rim' if v else 'coordinate-subject')}")
        if len(ties) > 1:
            print("     An UNDETERMINED axis has no rows on this data that could "
                  "separate the\n     candidates. Cite the pipeline SOURCE for it, "
                  "and say in the appendix\n     that the choice is empirically immaterial.")
    else:
        print(f"\n  -> NO combination reproduces the artifact "
              f"(best {best['agreement']:.6f}). Disagreements broken out below.")

    # -- 2. disagreement anatomy ---------------------------------------------
    d = df.with_columns(
        derive_bucket(best["corner_depth"], best["rim_strict_lt"],
                      best["rim_actions_always_at_rim"])
    )
    bad = d.filter(~pl.col("bucket").eq_missing(pl.col("derived")))
    print("\n" + "-" * 78)
    print(f"2. DISAGREEMENTS under the best rule set: {bad.height:,}")
    print("-" * 78)
    if bad.height:
        pairs = (bad.group_by(["bucket", "derived", "ID_ACTION"]).len()
                    .sort("len", descending=True).head(25))
        print(pairs)
        by_season = bad.group_by("Season").len().sort("Season")
        print("\nby season:")
        print(by_season)
        report["disagreement_pairs"] = pairs.to_dicts()
        report["disagreement_by_season"] = by_season.to_dicts()
        bad.write_csv(outdir / "tagging_disagreements.csv")
        print(f"\nfull disagreement set -> {outdir / 'tagging_disagreements.csv'}")
    else:
        print("  none -- every stored label is reproducible from the pinned rules.")
        report["disagreement_pairs"] = []

    # -- 3. action-code vocabulary by season (Ch5 s5.2.5) --------------------
    print("\n" + "-" * 78)
    print("3. ACTION-CODE VOCABULARY BY SEASON")
    print("-" * 78)
    codes = df.group_by(["Season", "ID_ACTION"]).len()
    tot = df.group_by("Season").len().rename({"len": "season_n"})
    codes = (codes.join(tot, on="Season")
                  .with_columns((pl.col("len") / pl.col("season_n")).alias("share"))
                  .sort(["Season", "len"], descending=[False, True]))
    pivot = codes.pivot(on="ID_ACTION", index="Season", values="len").fill_null(0).sort("Season")
    with pl.Config(tbl_cols=-1, tbl_rows=-1, tbl_width_chars=200):
        print(pivot)
    codes.write_csv(outdir / "action_code_census.csv")
    report["action_codes"] = sorted(df["ID_ACTION"].unique().to_list())

    unhandled = [c for c in report["action_codes"] if c not in FG_ATTEMPTS]
    print(f"\ncodes present: {report['action_codes']}")
    if unhandled:
        print(f"!! CODES WITH NO RULE (route to null): {unhandled}")
    report["unhandled_codes"] = unhandled

    routing = (df.group_by(["ID_ACTION", "bucket"]).len()
                 .sort(["ID_ACTION", "len"], descending=[False, True]))
    print("\nhow each code routes:")
    with pl.Config(tbl_rows=-1):
        print(routing)
    report["code_routing"] = routing.to_dicts()

    # -- 4. flags are genuinely ignored --------------------------------------
    print("\n" + "-" * 78)
    print("4. FASTBREAK / SECOND_CHANCE -- confirm precedence is gone")
    print("-" * 78)
    fl = df.with_columns(
        flag_expr("FASTBREAK").alias("fb"), flag_expr("SECOND_CHANCE").alias("sc")
    )
    for name in ("fb", "sc"):
        sub = fl.filter(pl.col(name))
        n = sub.height
        misses = sub.filter(pl.col("points") == 0).height if n else 0
        mix = sub.group_by("bucket").len().sort("len", descending=True) if n else None
        print(f"\n{name}: {n:,} rows, {misses:,} with points == 0")
        if mix is not None:
            print(mix)
        report[f"flag_{name}"] = {
            "rows": n, "zero_point_rows": misses,
            "mix": {r["bucket"]: r["len"] for r in mix.to_dicts()} if mix is not None else {},
        }
    print("\n  Flagged rows spread across LOCATION buckets = precedence removed.")
    print("  Near-zero misses = flags are made-shot-only, as recorded.")

    # -- 5. coordinate integrity / orientation by season (Ch9 s9.1) ----------
    print("\n" + "-" * 78)
    print("5. COORDINATE INTEGRITY AND ORIENTATION BY SEASON")
    print("-" * 78)
    r = _radius()
    geo = (
        df.with_columns(
            r.alias("r"),
            pl.col("ID_ACTION").is_in(sorted(THREE_ACTIONS)).alias("is3"),
        )
        .group_by("Season")
        .agg(
            pl.len().alias("n"),
            (pl.col("COORD_X").is_null() | pl.col("COORD_Y").is_null())
                .mean().alias("null_coord_rate"),
            (pl.col("r").filter(pl.col("is3")) < CORNER_SIDELINE_MIN)
                .mean().alias("three_inside_arc"),
            (pl.col("r").filter(~pl.col("is3")) > ARC)
                .mean().alias("two_beyond_arc"),
            ((pl.col("is3") & (pl.col("r") < CORNER_SIDELINE_MIN))
             | (~pl.col("is3") & (pl.col("r") > ARC))).mean().alias("orientation_fail"),
            pl.col("r").median().alias("r_median"),
            pl.col("r").max().alias("r_max"),
        )
        .sort("Season")
    )
    with pl.Config(tbl_rows=-1, tbl_width_chars=200):
        print(geo)
    overall = (
        df.with_columns(r.alias("r"),
                        pl.col("ID_ACTION").is_in(sorted(THREE_ACTIONS)).alias("is3"))
        .select(
            ((pl.col("r").filter(pl.col("is3")) < CORNER_SIDELINE_MIN).sum()
             + (pl.col("r").filter(~pl.col("is3")) > ARC).sum()) / pl.len()
        ).item()
    )
    print(f"\noverall orientation-failure rate: {overall:.5f}")
    report["orientation_overall"] = overall
    report["geometry_by_season"] = geo.to_dicts()
    geo.write_csv(outdir / "coordinate_integrity_by_season.csv")

    # boundary populations -- how many rows the disputed rules could ever move
    b220_225 = df.filter(
        pl.col("ID_ACTION").is_in(sorted(THREE_ACTIONS))
        & (pl.col("COORD_X").abs() >= CORNER_SIDELINE_MIN)
        & (pl.col("COORD_Y") > 220.0) & (pl.col("COORD_Y") <= 225.0)
    ).height
    b_rim = df.filter(r == RIM_RADIUS).height
    print(f"\nrows in the 220 < y <= 225 corner band: {b220_225:,}")
    print(f"rows exactly at r == 200: {b_rim:,}")
    report["boundary_corner_220_225"] = b220_225
    report["boundary_rim_exact"] = b_rim
    if b220_225 == 0:
        print("  -> the corner-depth dispute is EMPTY on this data; either value "
              "reproduces it. Cite the value the pipeline SOURCE uses.")

    # -- 6. optional manual-check sample -------------------------------------
    if a.sample:
        keep = [c for c in ("Season", "Gamecode", "NUM_ANOT", "TEAM", "PLAYER",
                            "ID_ACTION", "points", "FASTBREAK", "SECOND_CHANCE",
                            "COORD_X", "COORD_Y", "bucket") if c in df.columns]
        smp = (df.filter(pl.col("Season").is_in(a.sample_seasons))
                 .select(keep)
                 .with_columns(_radius().round(1).alias("r"))
                 .sample(min(a.sample * max(len(a.sample_seasons), 1), df.height),
                         seed=a.seed, shuffle=True)
                 .sort(["Season", "Gamecode", "NUM_ANOT"]))
        path = outdir / "tagging_manual_sample.csv"
        smp.write_csv(path)
        print(f"\nmanual-check sample ({smp.height} rows, seasons "
              f"{a.sample_seasons}) -> {path}")
        print("  Carries the STORED bucket. Check against the official shot chart;"
              "\n  this is the only test that can catch a consistent mis-orientation.")

    (outdir / "validate_tagging_4b.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\nJSON -> {outdir / 'validate_tagging_4b.json'}")

    print("\n" + "=" * 78)
    ok = (best["agreement"] == 1.0 and not unexpected and not unhandled)
    print("VERDICT: PASS -- taxonomy reproducible, vocabulary fully routed."
          if ok else
          "VERDICT: REVIEW -- see sections above before writing the appendix.")
    print("=" * 78)


if __name__ == "__main__":
    main()
