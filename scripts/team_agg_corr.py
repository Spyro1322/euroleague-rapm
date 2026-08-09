#!/usr/bin/env python3
"""
team_agg_corr.py -- Ch7 flag: do the box-score arms sit on the unadjusted side?

Ch7 argues that RAPM under-predicts game margin BECAUSE it de-confounds team
context, and that the box-score arms retain that context and are rewarded for it
on a margin-prediction task. Olivo reports the same property from the other side:
RAPM correlates with team record at 0.599 against raw plus-minus at 0.783.

This tests the mechanism internally. Each arm's player ratings are aggregated to
the team-season by minutes, and correlated with team win percentage over
2020-2024 -- the RAPM training window, NOT the held-out season.

EXPECTED ORDERING (state before looking):
    raw plus-minus  >  PIR ~ Win Score  >  RAPM
A rating that carries team context correlates with team record. One that removes
it should not. If RAPM lands as high as the box-score arms, the Ch7 s7.8
mechanism is wrong and needs rewriting -- that is the point of running it.

NOTE ON CAUSALITY: this is a descriptive correlation over ~90 team-seasons, not
a claim that de-confounding causes the margin-prediction gap. It establishes that
the arms differ in the property s7.8 says they differ in.

USAGE
    python3 scripts/team_agg_corr.py --lo 2020 --hi 2024
"""
from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

ARMS = {
    "plusminus": "pm_per40_z",
    "pir": "pir_per40_z",
    "win_score": "ws_per40_z",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", default="warehouse")
    ap.add_argument("--lo", type=int, default=2020)
    ap.add_argument("--hi", type=int, default=2024)
    ap.add_argument("--rapm-stem", default="rapm_eval_full")
    ap.add_argument("--min-minutes", type=float, default=200.0,
                    help="team-season minutes floor for a player to be aggregated")
    ap.add_argument("--out", default="reports/team_agg_corr.txt")
    a = ap.parse_args()
    W = Path(a.warehouse)
    yrs = (pl.col("Season") >= a.lo) & (pl.col("Season") <= a.hi)

    print("=" * 74)
    print(f"TEAM-AGGREGATE CORRELATION vs WIN PCT -- seasons {a.lo}-{a.hi}")
    print("=" * 74)

    # -- 1. team-season win pct, from stint-level scores ---------------------
    st = pl.read_parquet(W / "stints.parquet").filter(yrs)
    games = (
        st.group_by(["Season", "Gamecode"])
          .agg(pl.col("home_team").first(), pl.col("away_team").first(),
               pl.col("home_pts").sum(), pl.col("away_pts").sum())
          .filter(pl.col("home_pts") != pl.col("away_pts"))
    )
    print(f"games: {games.height:,}")

    home = games.select(
        pl.col("Season"), pl.col("home_team").alias("team"),
        (pl.col("home_pts") > pl.col("away_pts")).cast(pl.Int8).alias("win"))
    away = games.select(
        pl.col("Season"), pl.col("away_team").alias("team"),
        (pl.col("away_pts") > pl.col("home_pts")).cast(pl.Int8).alias("win"))
    rec = (pl.concat([home, away])
             .group_by(["Season", "team"])
             .agg(pl.len().alias("g"), pl.col("win").sum().alias("w"))
             .with_columns((pl.col("w") / pl.col("g")).alias("win_pct")))
    print(f"team-seasons: {rec.height}  (median {rec['g'].median():.0f} games)")

    # -- 2. player -> team-season, from the play-by-play ---------------------
    # The boxscore table carries no team, so affiliation is taken as the modal
    # team code on a player's play-by-play rows within the season.
    pbp = (pl.scan_parquet(W / "pbp_poss.parquet")
             .filter(yrs)
             .select(["Season", "PLAYER_ID", "CODETEAM"])
             .filter(pl.col("PLAYER_ID").is_not_null()
                     & (pl.col("PLAYER_ID").str.strip_chars() != "")
                     & pl.col("CODETEAM").is_not_null())
             .with_columns(pl.col("PLAYER_ID").str.strip_chars().alias("player_id"),
                           pl.col("CODETEAM").str.strip_chars().alias("team"))
             .group_by(["Season", "player_id", "team"]).len()
             .collect())
    aff = (pbp.sort("len", descending=True)
              .unique(subset=["Season", "player_id"], keep="first")
              .select(["Season", "player_id", "team"]))
    print(f"player-season affiliations: {aff.height:,}")

    unmatched = aff.join(rec, on=["Season", "team"], how="anti")
    if unmatched.height:
        print(f"  !! {unmatched.height} affiliations whose team code is absent "
              f"from the stint records -- check code spaces match:")
        print(unmatched.select("team").unique().head(10))

    # -- 3. box-score arms ---------------------------------------------------
    bs = (pl.read_parquet(W / "eval_boxscore_metrics.parquet")
            .filter(yrs)
            .with_columns(pl.col("Player_ID").str.strip_chars().alias("player_id"))
            .select(["Season", "player_id", "minutes"] + list(ARMS.values())))
    print(f"boxscore player-seasons: {bs.height:,}")

    # -- 4. RAPM arm ---------------------------------------------------------
    # One rating per player for the whole window, so the same value is carried
    # into each of that player's team-seasons. Stated in the chapter.
    rp = (pl.read_parquet(W / f"{a.rapm_stem}.parquet")
            .select(["player_id", "RAPM"])
            .with_columns(pl.col("player_id").str.strip_chars()))
    print(f"rapm players ({a.rapm_stem}): {rp.height:,}")

    df = (bs.join(aff, on=["Season", "player_id"], how="inner")
            .join(rp, on="player_id", how="left"))
    cov = df.filter(pl.col("RAPM").is_not_null())["minutes"].sum() / df["minutes"].sum()
    print(f"joined player-seasons: {df.height:,}   "
          f"RAPM minute coverage: {cov:.1%}")
    if cov < 0.5:
        print("  !! low coverage -- check the player_id join before trusting the RAPM row")

    df = df.filter(pl.col("minutes") >= a.min_minutes)
    print(f"after {a.min_minutes:.0f}-minute floor: {df.height:,}")

    # -- 5. aggregate and correlate -----------------------------------------
    def wmean(col: str) -> pl.Expr:
        m = pl.col("minutes") * pl.col(col).is_not_null().cast(pl.Float64)
        return ((pl.col(col).fill_null(0.0) * m).sum() / m.sum()).alias(col)

    aggs = [wmean(c) for c in list(ARMS.values()) + ["RAPM"]]
    aggs.append(pl.col("minutes").sum().alias("team_minutes"))

    agg = (df.group_by(["Season", "team"])
             .agg(aggs)
             .join(rec, on=["Season", "team"], how="inner"))
    print(f"team-seasons with ratings: {agg.height}")

    rows = []
    for label, col in list(ARMS.items()) + [("rapm", "RAPM")]:
        sub = agg.filter(pl.col(col).is_not_null() & pl.col(col).is_finite())
        r = sub.select(pl.corr(pl.col(col), pl.col("win_pct"))).item()
        rows.append((label, r if r is not None else float("nan"), sub.height))

    rows.sort(key=lambda t: -abs(t[1]))
    lines = ["", f"{'arm':<14}{'corr with win pct':>20}{'team-seasons':>16}", "-" * 50]
    for label, r, n in rows:
        lines.append(f"{label:<14}{r:>20.3f}{n:>16}")
    lines += [
        "",
        "Reference: Olivo reports RAPM 0.599 against raw plus-minus 0.783 on a",
        "comparable exercise. The ordering, not the level, is the comparable part.",
    ]
    print("\n".join(lines))

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines) + "\n")
    agg.write_csv(Path(a.out).with_suffix(".csv"))
    print(f"\n-> {a.out} and {Path(a.out).with_suffix('.csv')}")


if __name__ == "__main__":
    main()