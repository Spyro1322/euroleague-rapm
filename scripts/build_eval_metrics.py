"""
scripts/build_eval_metrics.py

Builds the box-score baselines the held-out evaluation compares RAPM against:
PIR (the competition's official efficiency rating) and Win Score (Berri).

WHY THESE TWO
PIR is the metric this thesis argues against in Chapter 1: it is the number the
competition publishes, the number awards are decided on, and the number a
practitioner actually sees. An evaluation that beats a metric nobody uses proves
nothing. Win Score is included as a second box-score baseline from the academic
literature, constructed on different weights, so that the comparison is against
the box-score APPROACH rather than against one particular formula.

RATE ADJUSTMENT
Both are counting statistics: they reward minutes. A rating used to predict a
possession's outcome must be a rate, or the comparison degenerates into "who
plays more", which RAPM does not claim to measure. Both are therefore expressed
per 40 minutes -- the regulation game length -- and standardised within season,
since scoring environment drifts across the study period.

VERIFICATION
The boxscore carries a Valuation column, which is the competition's own PIR.
Rather than trust it or replace it, this script recomputes PIR from components
and checks the two agree. A mismatch means either the formula here is wrong or
the feed's convention differs from the published one, and both are worth knowing
before a chapter is written around the number.

    python3 scripts/build_eval_metrics.py --seasons 2020-2025
"""

import argparse
from pathlib import Path

import polars as pl

BOX_GLOB = "landing/boxscore_players/**/*.parquet"
OUT = "warehouse/eval_boxscore_metrics.parquet"

# Minutes played below which a player-season is excluded from rate statistics.
# A rate computed on a handful of minutes is dominated by its denominator.
MIN_MINUTES = 200


def parse_minutes(col: str) -> pl.Expr:
    """'MM:SS' -> float minutes. DNPs appear as null or an empty string."""
    s = pl.col(col).cast(pl.Utf8).str.strip_chars()
    mm = s.str.split(":").list.get(0, null_on_oob=True).cast(pl.Float64, strict=False)
    ss = s.str.split(":").list.get(1, null_on_oob=True).cast(pl.Float64, strict=False)
    return (mm + ss / 60.0).fill_null(0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2007-2025", help="e.g. 2020-2025")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.seasons.split("-")) if "-" in args.seasons \
        else (int(args.seasons), int(args.seasons))

    df = pl.read_parquet(BOX_GLOB).filter(
        (pl.col("Season") >= lo) & (pl.col("Season") <= hi))
    print(f"boxscore rows {lo}-{hi}: {df.height:,}")

    df = df.with_columns([
        # build_player_id_map.py strips this column before building the canonical
        # map, so the ids in stints_ids are stripped. Not stripping here produces
        # a disjoint id space and every downstream lookup silently misses.
        pl.col("Player_ID").cast(pl.Utf8).str.strip_chars().alias("Player_ID"),
        parse_minutes("Minutes").alias("min"),
        (pl.col("FieldGoalsAttempted2") + pl.col("FieldGoalsAttempted3")).alias("fga"),
        (pl.col("FieldGoalsMade2") + pl.col("FieldGoalsMade3")).alias("fgm"),
    ])

    # ---- PIR, recomputed from components
    pir = (
        pl.col("Points") + pl.col("TotalRebounds") + pl.col("Assistances")
        + pl.col("Steals") + pl.col("BlocksFavour") + pl.col("FoulsReceived")
        - (pl.col("fga") - pl.col("fgm"))
        - (pl.col("FreeThrowsAttempted") - pl.col("FreeThrowsMade"))
        - pl.col("Turnovers") - pl.col("BlocksAgainst") - pl.col("FoulsCommited")
    )

    # ---- Win Score (Berri)
    ws = (
        pl.col("Points") + pl.col("TotalRebounds") + pl.col("Steals")
        + 0.5 * pl.col("Assistances") + 0.5 * pl.col("BlocksFavour")
        - pl.col("fga") - 0.5 * pl.col("FreeThrowsAttempted")
        - pl.col("Turnovers") - 0.5 * pl.col("FoulsCommited")
    )

    df = df.with_columns([pir.alias("pir_calc"), ws.alias("win_score")])

    # ---- verification against the feed's own Valuation column
    print("\nPIR verification (recomputed vs the feed's Valuation column):")
    if "Valuation" not in df.columns:
        print("  !! no Valuation column — cannot verify.")
    else:
        chk = df.filter(pl.col("min") > 0).with_columns(
            (pl.col("pir_calc") - pl.col("Valuation")).alias("d"))
        n_bad = chk.filter(pl.col("d") != 0).height
        print(f"  rows compared: {chk.height:,}   disagreements: {n_bad:,} "
              f"({100*n_bad/max(chk.height,1):.3f}%)")
        if n_bad:
            print("  disagreement distribution:")
            print(chk.filter(pl.col("d") != 0).group_by("d").agg(pl.len().alias("n"))
                  .sort("n", descending=True).head(8))
            print(chk.filter(pl.col("d") != 0).group_by("Season").agg(pl.len().alias("n"))
                  .sort("Season"))
            print("  >>> Investigate before writing a chapter around PIR. A constant")
            print("      offset means a component is weighted differently here; a")
            print("      season-clustered pattern means the competition changed the")
            print("      formula, which is itself worth a sentence.")
        else:
            print("  >>> exact agreement — the recomputed formula matches the "
                  "competition's published definition.")

    # ---- aggregate to player-season
    ps = (df.group_by(["Season", "Player_ID"]).agg([
            pl.col("Player").first().alias("name"),
            pl.len().alias("games"),
            pl.col("min").sum().alias("minutes"),
            pl.col("pir_calc").sum().alias("pir_total"),
            pl.col("win_score").sum().alias("ws_total"),
            pl.col("Plusminus").sum().alias("plusminus_total"),
        ])
        .filter(pl.col("minutes") >= MIN_MINUTES)
        .with_columns([
            (40.0 * pl.col("pir_total") / pl.col("minutes")).alias("pir_per40"),
            (40.0 * pl.col("ws_total") / pl.col("minutes")).alias("ws_per40"),
            (40.0 * pl.col("plusminus_total") / pl.col("minutes")).alias("pm_per40"),
        ]))
    print(f"\nplayer-seasons with >= {MIN_MINUTES} minutes: {ps.height:,}")

    # ---- standardise within season: the scoring environment drifts across the
    # study period, and an unstandardised rate would let era masquerade as skill.
    ps = ps.with_columns([
        ((pl.col(c) - pl.col(c).mean().over("Season"))
         / pl.col(c).std().over("Season")).alias(c + "_z")
        for c in ("pir_per40", "ws_per40", "pm_per40")
    ])

    print("\nper-season summary:")
    print(ps.group_by("Season").agg([
        pl.len().alias("players"),
        pl.col("pir_per40").mean().round(2).alias("pir40_mean"),
        pl.col("pir_per40").std().round(2).alias("pir40_sd"),
        pl.col("ws_per40").mean().round(2).alias("ws40_mean"),
    ]).sort("Season"))

    # ---- how much do the two box-score metrics actually differ?
    c = ps.select(pl.corr("pir_per40", "ws_per40")).item()
    print(f"\ncorr(PIR/40, WinScore/40) = {c:.3f}")
    if c > 0.95:
        print("  >>> The two box-score baselines are nearly the same measurement.")
        print("      Report them as one approach with two weightings rather than as")
        print("      two independent points of comparison — an evaluation that beats")
        print("      both has beaten one thing, not two.")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    ps.write_parquet(args.out)
    print(f"\nwrote {args.out}  ({ps.height:,} player-seasons)")
    print("\ncolumns: Season, Player_ID, name, games, minutes, "
          "pir_per40, ws_per40, pm_per40 (+ _z standardised within season)")
    print("\nnext: evaluate_holdout.py — aggregate these to 2025-26 lineups and "
          "compare against RAPM on out-of-sample stint outcomes.")


if __name__ == "__main__":
    main()