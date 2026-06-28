"""
qc_lineups.py — quantify corrupt-lineup rows the substitution matcher produces.

`five_invariant` checked length==5; this checks DISTINCTNESS==5, the failure mode
that slips through (duplicated player name = 4 real players + a phantom). Run it
over the ingested parquet to size the problem before deciding how to exclude it.

    python scripts/qc_lineups.py --glob "data/pbp_lineups/**/*.parquet"
"""
from __future__ import annotations
import argparse
import polars as pl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/pbp_lineups/**/*.parquet")
    a = ap.parse_args()

    df = pl.read_parquet(a.glob)
    df = df.with_columns(
        pl.col("Lineup_A").list.n_unique().alias("nA"),
        pl.col("Lineup_B").list.n_unique().alias("nB"),
    ).with_columns(
        ((pl.col("nA") == 5) & (pl.col("nB") == 5)).alias("lineup_ok")
    )

    n = df.height
    bad = df.filter(~pl.col("lineup_ok"))
    # count GAMES as distinct (Season, Gamecode) pairs — Gamecode repeats across seasons
    bad_games = bad.select(["Season", "Gamecode"]).unique().height
    tot_games = df.select(["Season", "Gamecode"]).unique().height
    print(f"rows total            : {n:,}")
    print(f"rows with corrupt five: {bad.height:,}  ({100*bad.height/n:.3f}%)")
    print(f"games affected        : {bad_games} of {tot_games}  "
          f"({100*bad_games/tot_games:.2f}% of games)")

    print("\nworst games (corrupt rows, share of that game):")
    per_game = (
        df.group_by(["Season", "Gamecode"])
          .agg(
              pl.len().alias("rows"),
              (~pl.col("lineup_ok")).sum().alias("bad_rows"),
          )
          .filter(pl.col("bad_rows") > 0)
          .with_columns((pl.col("bad_rows") / pl.col("rows")).alias("share"))
          .sort("bad_rows", descending=True)
    )
    print(per_game.head(15))

    # does the existing attribution flag overlap with composition corruption?
    if "validate_on_court_player" in df.columns:
        overlap = bad.filter(~pl.col("validate_on_court_player")).height
        print(f"\nof {bad.height} corrupt-five rows, {overlap} also have "
              f"validate_on_court_player=False → {bad.height - overlap} are "
              f"INVISIBLE to the existing flag (the reason a separate QC is needed)")


if __name__ == "__main__":
    main()