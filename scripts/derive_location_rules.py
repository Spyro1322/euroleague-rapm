"""
scripts/derive_location_rules.py

Recovers the shot-location bucket boundaries from the ALREADY-VALIDATED labels in
tagged_shots_ids, verifies the recovered rules reproduce those labels, and then
applies them to the rows that precedence stole — producing a corrected
four-bucket, location-only dataset without re-running the tagger.

WHY THIS IS SOUND
The tagger's location logic was manually validated in Week 2 (20 possessions x 5
games). Its OUTPUT for the four location buckets is therefore trustworthy. What
this script does is fit boundaries to that trusted output and report the purity of
the fit. If purity is ~100%, the recovered rules ARE the tagger's rules for
practical purposes, and applying them to the transition/second_chance rows is
just finishing a classification the tagger declined to make because a situation
flag took precedence.

If purity is materially below ~99.5% the recovered rules are NOT the tagger's
rules — the real logic uses something this script isn't modelling (a piecewise
boundary, a corner definition keyed off a different axis, a special case for
dunks) and you should take the thresholds from the source instead of from here.
The script says so explicitly rather than quietly proceeding.

WHAT ONLY NEEDS TWO NUMBERS
ID_ACTION already separates 2FG from 3FG, so the 2-vs-3 decision is free:
    2FGA/2FGM -> at_rim | mid_range      split by distance from the basket
    3FGA/3FGM -> corner_three | above_break_three   split by the corner region
So there are two boundaries to find, not a six-way classifier.

OUTPUT
    reports/location_rules.json         the recovered thresholds + purity
    warehouse/tagged_shots_ids_4b.parquet   corrected four-bucket labels,
        every shot classified by location only, situation flags ignored

Feed the corrected file to the design builder:
    python3 scripts/build_shotctx_design.py --window baseline \
        --shots warehouse/tagged_shots_ids_4b.parquet
"""

import json
from pathlib import Path

import numpy as np
import polars as pl

W = Path("warehouse")
R = Path("reports")

LOC2 = ["at_rim", "mid_range"]
LOC3 = ["corner_three", "above_break_three"]
SITUATION = ["transition", "second_chance"]
TWO_PT = ["2FGA", "2FGM"]
THREE_PT = ["3FGA", "3FGM"]


def hr(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def load():
    df = pl.read_parquet(W / "tagged_shots_ids.parquet")
    df = df.with_columns([
        pl.col("COORD_X").cast(pl.Float64).alias("x"),
        pl.col("COORD_Y").cast(pl.Float64).alias("y"),
    ]).with_columns(
        (pl.col("x") ** 2 + pl.col("y") ** 2).sqrt().alias("r")
    )
    return df


def describe_geometry(df: pl.DataFrame):
    hr("1. COORDINATE SYSTEM")
    print(f"  rows: {df.height:,}")
    for c in ("x", "y", "r"):
        s = df[c]
        qs = [s.quantile(q) for q in (0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0)]
        print(f"  {c}: " + "  ".join(f"{q:8.1f}" for q in qs)
              + "   (min p1 p25 p50 p75 p99 max)")
    print("\n  per-bucket geometry (median |x|, median y, median r):")
    g = df.with_columns(pl.col("x").abs().alias("ax")).group_by("bucket").agg([
        pl.len().alias("n"),
        pl.col("ax").median().alias("|x|_med"),
        pl.col("y").median().alias("y_med"),
        pl.col("r").median().alias("r_med"),
        pl.col("r").quantile(0.05).alias("r_p05"),
        pl.col("r").quantile(0.95).alias("r_p95"),
    ]).sort("r_med")
    print(g)
    print("\n  >>> If y is never negative and r_med for at_rim is small, the origin is")
    print("      the basket and r is distance from it. That is the assumption below.")


def fit_threshold_1d(vals_a: np.ndarray, vals_b: np.ndarray, name_a: str, name_b: str,
                     lo=None, hi=None, steps=400):
    """
    Find the cut t maximizing agreement with: a := val < t, b := val >= t.
    Returns (t, purity, detail). Handles the case where a should be ABOVE instead.
    """
    allv = np.concatenate([vals_a, vals_b])
    lo = np.nanpercentile(allv, 0.5) if lo is None else lo
    hi = np.nanpercentile(allv, 99.5) if hi is None else hi
    grid = np.linspace(lo, hi, steps)
    n = len(vals_a) + len(vals_b)

    best = (None, -1.0, None)
    for t in grid:
        # orientation 1: a below, b at-or-above
        c1 = (vals_a < t).sum() + (vals_b >= t).sum()
        # orientation 2: a at-or-above, b below
        c2 = (vals_a >= t).sum() + (vals_b < t).sum()
        if c1 >= c2:
            acc, orient = c1 / n, f"{name_a} < t <= {name_b}"
        else:
            acc, orient = c2 / n, f"{name_b} < t <= {name_a}"
        if acc > best[1]:
            best = (float(t), float(acc), orient)
    return best


def fit_corner(df3: pl.DataFrame):
    """
    Corner threes are conventionally defined by a band near the baseline: |x| large
    AND y small. Scan a 2D grid over (|x| min, y max) and report the best cell.
    """
    ax = df3["x"].abs().to_numpy()
    y = df3["y"].to_numpy()
    is_corner = (df3["bucket"] == "corner_three").to_numpy()

    ax_grid = np.percentile(ax, np.linspace(50, 99.5, 60))
    y_grid = np.percentile(y, np.linspace(0.5, 60, 60))
    n = len(ax)

    best = (None, None, -1.0)
    for axt in ax_grid:
        for yt in y_grid:
            pred = (ax >= axt) & (y <= yt)
            acc = (pred == is_corner).mean()
            if acc > best[2]:
                best = (float(axt), float(yt), float(acc))

    # also try a y-only rule, which is what many definitions reduce to
    y_only = fit_threshold_1d(
        y[is_corner], y[~is_corner], "corner", "above_break")
    return best, y_only


def main():
    df = load()
    describe_geometry(df)

    # ---------------------------------------------------------------- 2FG rule
    hr("2. AT_RIM vs MID_RANGE  (among 2-point attempts)")
    d2 = df.filter(pl.col("bucket").is_in(LOC2))
    print(f"  labelled 2FG location rows: {d2.height:,}")
    bad_action = d2.filter(~pl.col("ID_ACTION").is_in(TWO_PT))
    if bad_action.height:
        print(f"  !! {bad_action.height:,} rows labelled at_rim/mid_range are NOT 2FG codes:")
        print(bad_action.group_by("ID_ACTION").agg(pl.len()).sort("len", descending=True))
        print("     The 2-vs-3 split is therefore not purely ID_ACTION-driven.")

    r_rim = d2.filter(pl.col("bucket") == "at_rim")["r"].to_numpy()
    r_mid = d2.filter(pl.col("bucket") == "mid_range")["r"].to_numpy()
    t_rim, acc_rim, orient_rim = fit_threshold_1d(r_rim, r_mid, "at_rim", "mid_range")
    print(f"\n  best radius cut: r = {t_rim:.1f}   ({orient_rim})")
    print(f"  purity: {acc_rim:.5f}")
    mis = int(round((1 - acc_rim) * (len(r_rim) + len(r_mid))))
    print(f"  misclassified under this rule: {mis:,} of {len(r_rim)+len(r_mid):,}")
    print(f"  at_rim   r: p05={np.percentile(r_rim,5):.0f} med={np.median(r_rim):.0f} "
          f"p95={np.percentile(r_rim,95):.0f}")
    print(f"  mid_range r: p05={np.percentile(r_mid,5):.0f} med={np.median(r_mid):.0f} "
          f"p95={np.percentile(r_mid,95):.0f}")

    # ---------------------------------------------------------------- 3FG rule
    hr("3. CORNER_THREE vs ABOVE_BREAK_THREE  (among 3-point attempts)")
    d3 = df.filter(pl.col("bucket").is_in(LOC3))
    print(f"  labelled 3FG location rows: {d3.height:,}")
    (axt, yt, acc2d), (ty, accy, orienty) = fit_corner(d3)
    print(f"\n  2D rule: corner  <=>  |x| >= {axt:.1f}  AND  y <= {yt:.1f}")
    print(f"  purity: {acc2d:.5f}")
    print(f"\n  1D fallback (y only): cut y = {ty:.1f}  ({orienty})")
    print(f"  purity: {accy:.5f}")
    use_2d = acc2d >= accy
    print(f"\n  >>> using the {'2D' if use_2d else '1D y-only'} rule")

    # ---------------------------------------------------------------- verdict
    hr("4. ARE THE RECOVERED RULES THE TAGGER'S RULES?")
    corner_acc = acc2d if use_2d else accy
    print(f"  at_rim / mid_range purity      : {acc_rim:.5f}")
    print(f"  corner / above_break purity    : {corner_acc:.5f}")
    ok = acc_rim >= 0.995 and corner_acc >= 0.995
    if ok:
        print("\n  >>> BOTH >= 0.995. The recovered rules reproduce the validated labels.")
        print("      Safe to apply them to the situation-flagged rows.")
    else:
        print("\n  >>> PURITY TOO LOW. The recovered rules are NOT the tagger's rules.")
        print("      Something in the real logic isn't captured here (piecewise boundary,")
        print("      a different corner axis, a dunk/putback special case). Take the")
        print("      thresholds from the tagger source instead of from this fit.")
        print("      The corrected file below is still written, but DO NOT trust it")
        print("      until the purity question is settled.")

    # ---------------------------------------------------------------- reclassify
    hr("5. RECLASSIFYING THE SITUATION-FLAGGED ROWS")
    sit = df.filter(pl.col("bucket").is_in(SITUATION))
    print(f"  rows to reclassify: {sit.height:,}")
    print(sit.group_by(["bucket", "ID_ACTION"]).agg(pl.len().alias("n"))
          .sort(["bucket", "n"], descending=[False, True]))

    is3 = pl.col("ID_ACTION").is_in(THREE_PT)
    if use_2d:
        corner_expr = (pl.col("x").abs() >= axt) & (pl.col("y") <= yt)
    else:
        # honour the orientation the 1D fit chose
        corner_expr = (pl.col("y") <= ty) if "corner < t" in orienty else (pl.col("y") > ty)

    relabel = (
        pl.when(is3 & corner_expr).then(pl.lit("corner_three"))
         .when(is3).then(pl.lit("above_break_three"))
         .when(pl.col("r") < t_rim).then(pl.lit("at_rim"))
         .otherwise(pl.lit("mid_range"))
    )

    out = df.with_columns(relabel.alias("bucket_4b"))
    moved = out.filter(pl.col("bucket").is_in(SITUATION))
    print("\n  where the reclaimed shots went:")
    print(moved.group_by(["bucket", "bucket_4b"]).agg(pl.len().alias("n"))
          .sort(["bucket", "n"], descending=[False, True]))

    # sanity: do the recovered rules agree with existing labels on rows we did NOT move?
    kept = out.filter(~pl.col("bucket").is_in(SITUATION))
    agree = kept.filter(pl.col("bucket") == pl.col("bucket_4b")).height
    print(f"\n  agreement on already-located rows: {agree:,}/{kept.height:,} "
          f"= {agree/kept.height:.5f}")
    print("  (this is the same purity measured end-to-end through the actual expression)")

    # ---------------------------------------------------------------- efficiency check
    hr("6. DOES THE CORRECTION MOVE FG% TOWARD LEAGUE NORMS?")
    def eff(frame, col):
        return (frame.group_by(col).agg([
            pl.len().alias("att"),
            (pl.col("points") > 0).sum().alias("made"),
            pl.col("points").sum().alias("pts"),
        ]).with_columns([
            (pl.col("made") / pl.col("att")).alias("fg_pct"),
            (100 * pl.col("pts") / pl.col("att")).alias("pts_per_100"),
        ]).sort(col))

    print("  BEFORE (precedence applied, situation buckets excluded):")
    print(eff(df.filter(pl.col("bucket").is_in(LOC2 + LOC3)), "bucket"))
    print("\n  AFTER (four buckets, all shots, flags ignored):")
    print(eff(out, "bucket_4b"))
    print("\n  >>> Expect at_rim FG% to rise sharply (reclaimed made layups/dunks) and")
    print("      above_break_three to rise toward ~0.35. If at_rim lands near 0.60-0.65")
    print("      and the threes near 0.35-0.40, the correction is behaving.")

    # ---------------------------------------------------------------- write
    hr("7. WRITING OUTPUTS")
    R.mkdir(exist_ok=True)
    rules = dict(
        at_rim_radius=t_rim,
        at_rim_purity=acc_rim,
        corner_rule="2d" if use_2d else "1d_y",
        corner_abs_x_min=axt if use_2d else None,
        corner_y_max=yt if use_2d else ty,
        corner_purity=corner_acc,
        end_to_end_agreement=agree / kept.height,
        two_pt_codes=TWO_PT, three_pt_codes=THREE_PT,
        trustworthy=bool(ok),
        note=("Recovered by fitting boundaries to the Week 2 manually-validated "
              "tagger output. Situation flags (FASTBREAK/SECOND_CHANCE) are ignored "
              "entirely: they are populated on made shots only and cannot support "
              "efficiency estimation."),
    )
    (R / "location_rules.json").write_text(json.dumps(rules, indent=2))
    print(f"  reports/location_rules.json")

    final = (out.drop("bucket").rename({"bucket_4b": "bucket"})
                .drop(["x", "y", "r"]))
    final.write_parquet(W / "tagged_shots_ids_4b.parquet")
    print(f"  warehouse/tagged_shots_ids_4b.parquet  ({final.height:,} rows)")
    print(final.group_by("bucket").agg(pl.len().alias("n")).sort("n", descending=True))

    print("\n  next:")
    print("    python3 scripts/build_shotctx_design.py --window dash \\")
    print("        --shots warehouse/tagged_shots_ids_4b.parquet")


if __name__ == "__main__":
    main()
