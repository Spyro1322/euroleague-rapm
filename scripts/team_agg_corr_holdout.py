#!/usr/bin/env python3
"""
team_agg_corr_holdout.py -- does team-level signal TRANSFER out of window?

Companion to team_agg_corr.py, which found, in-window on 2020-2024:

    plusminus 0.936  >  rapm 0.785  >  win_score 0.689  >  pir 0.666

That ordering falsified the de-confounding account in Ch7 s7.8: RAPM tracks
team record BETTER than the box-score arms, not worse. The natural reading is
that RAPM is fitted on the point differential of those very games, so
team-aggregating it partly reconstructs the margin the ridge distributed across
players. The correlation is in-sample by construction.

This script tests that reading. Every arm is frozen on 2020-2024 and correlated
against team win percentage in the HELD-OUT 2025-26 season, using that season's
rosters and minutes. No arm sees the held-out season.

PREDICTION, stated before running:
    RAPM's advantage over the box-score arms should shrink or invert. If the
    in-window ordering merely persists, the overfitting account is wrong too and
    s7.8 needs a third explanation.

TWO CORRELATIONS ARE REPORTED and the second is the honest one:
  - full      : each arm aggregated over whatever players it rates
  - common    : restricted to players rated by EVERY arm
The arms have different coverage (RAPM 677 players against a wider box-score
population), and coverage differences alone can move a team aggregate. Ch7
already notes this trap on the 73-game common-support subset.

USAGE
    python3 scripts/team_agg_corr_holdout.py --train-lo 2020 --train-hi 2024 \
                                             --eval-season 2025
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
    ap.add_argument("--train-lo", type=int, default=2020)
    ap.add_argument("--train-hi", type=int, default=2024)
    ap.add_argument("--eval-season", type=int, default=2025)
    ap.add_argument("--rapm-stem", default="rapm_eval_full")
    ap.add_argument("--out", default="reports/team_agg_corr_holdout.txt")
    a = ap.parse_args()
    W = Path(a.warehouse)
    E = a.eval_season

    print("=" * 74)
    print(f"OUT-OF-SAMPLE TEAM AGGREGATION -- trained {a.train_lo}-{a.train_hi}, "
          f"evaluated on {E}")
    print("=" * 74)

    # -- 1. held-out team-season win pct ------------------------------------
    st = pl.read_parquet(W / "stints.parquet").filter(pl.col("Season") == E)
    if st.height == 0:
        raise SystemExit(f"no stint rows for Season {E}; check the season code")
    games = (st.group_by(["Season", "Gamecode"])
               .agg(pl.col("home_team").first(), pl.col("away_team").first(),
                    pl.col("home_pts").sum(), pl.col("away_pts").sum())
               .filter(pl.col("home_pts") != pl.col("away_pts")))
    home = games.select(pl.col("home_team").alias("team"),
                        (pl.col("home_pts") > pl.col("away_pts")).cast(pl.Int8).alias("win"))
    away = games.select(pl.col("away_team").alias("team"),
                        (pl.col("away_pts") > pl.col("home_pts")).cast(pl.Int8).alias("win"))
    rec = (pl.concat([home, away]).group_by("team")
             .agg(pl.len().alias("g"), pl.col("win").sum().alias("w"))
             .with_columns((pl.col("w") / pl.col("g")).alias("win_pct")))
    print(f"held-out games: {games.height:,}   teams: {rec.height}   "
          f"median {rec['g'].median():.0f} games")

    # -- 2. held-out rosters and exposure weights ---------------------------
    pbp = (pl.scan_parquet(W / "pbp_poss.parquet")
             .filter(pl.col("Season") == E)
             .select(["PLAYER_ID", "CODETEAM"])
             .filter(pl.col("PLAYER_ID").is_not_null()
                     & (pl.col("PLAYER_ID").str.strip_chars() != "")
                     & pl.col("CODETEAM").is_not_null())
             .with_columns(pl.col("PLAYER_ID").str.strip_chars().alias("player_id"),
                           pl.col("CODETEAM").str.strip_chars().alias("team"))
             .group_by(["player_id", "team"]).len()
             .collect())
    roster = (pbp.sort("len", descending=True)
                 .unique(subset=["player_id"], keep="first"))
    print(f"held-out players: {roster.height:,}")

    bs_all = (pl.read_parquet(W / "eval_boxscore_metrics.parquet")
                .with_columns(pl.col("Player_ID").str.strip_chars().alias("player_id")))
    have_eval_minutes = bs_all.filter(pl.col("Season") == E).height > 0

    if have_eval_minutes:
        wts = (bs_all.filter(pl.col("Season") == E)
                     .select(["player_id", pl.col("minutes").alias("weight")]))
        print("exposure weight: held-out minutes from the boxscore table")
    else:
        wts = roster.select(["player_id", pl.col("len").cast(pl.Float64).alias("weight")])
        print("!! boxscore table has no rows for the held-out season.")
        print("   Falling back to play-by-play appearance counts as the exposure")
        print("   weight. This is a proxy for minutes, not minutes. State it in Ch7.")

    roster = roster.select(["player_id", "team"]).join(wts, on="player_id", how="inner")
    print(f"players with team and weight: {roster.height:,}")

    # -- 3. frozen ratings, training window only ----------------------------
    tr = bs_all.filter((pl.col("Season") >= a.train_lo) & (pl.col("Season") <= a.train_hi))
    print(f"training player-seasons: {tr.height:,}")

    def wmean_over_seasons(col: str) -> pl.Expr:
        m = pl.col("minutes") * pl.col(col).is_not_null().cast(pl.Float64)
        return ((pl.col(col).fill_null(0.0) * m).sum() / m.sum()).alias(col)

    frozen_bs = (tr.group_by("player_id")
                   .agg([wmean_over_seasons(c) for c in ARMS.values()]
                        + [pl.col("minutes").sum().alias("train_minutes")]))
    frozen_rapm = (pl.read_parquet(W / f"{a.rapm_stem}.parquet")
                     .select(["player_id", "RAPM"])
                     .with_columns(pl.col("player_id").str.strip_chars()))
    print(f"frozen box-score players: {frozen_bs.height:,}   "
          f"frozen rapm players: {frozen_rapm.height:,}")

    df = (roster.join(frozen_bs, on="player_id", how="left")
                .join(frozen_rapm, on="player_id", how="left"))

    tot = df["weight"].sum()
    print("\nheld-out exposure covered by each frozen arm:")
    for label, col in list(ARMS.items()) + [("rapm", "RAPM")]:
        c = df.filter(pl.col(col).is_not_null())["weight"].sum() / tot
        print(f"  {label:<12}{c:>7.1%}")
    print("  Uncovered exposure is players who did not appear in the training")
    print("  window -- newcomers to the competition. Their teams are aggregated")
    print("  from a partial roster, which is itself a limitation worth stating.")

    cols = list(ARMS.values()) + ["RAPM"]
    common = df.filter(pl.all_horizontal([pl.col(c).is_not_null() for c in cols]))
    print(f"\nplayers rated by every arm: {common.height:,} of {df.height:,} "
          f"({common['weight'].sum()/tot:.1%} of exposure)")

    # -- 4. aggregate and correlate -----------------------------------------
    def aggregate(frame: pl.DataFrame) -> pl.DataFrame:
        def wm(col: str) -> pl.Expr:
            m = pl.col("weight") * pl.col(col).is_not_null().cast(pl.Float64)
            return ((pl.col(col).fill_null(0.0) * m).sum() / m.sum()).alias(col)
        aggs = [wm(c) for c in cols]
        aggs.append(pl.col("weight").sum().alias("team_weight"))
        return frame.group_by("team").agg(aggs).join(rec, on="team", how="inner")

    results = {}
    for name, frame in (("full", df), ("common", common)):
        agg = aggregate(frame)
        row = {}
        for label, col in list(ARMS.items()) + [("rapm", "RAPM")]:
            sub = agg.filter(pl.col(col).is_not_null() & pl.col(col).is_finite())
            r = sub.select(pl.corr(pl.col(col), pl.col("win_pct"))).item()
            row[label] = (r if r is not None else float("nan"), sub.height)
        results[name] = row
        agg.write_csv(Path(a.out).with_suffix(f".{name}.csv"))

    lines = ["", f"{'arm':<14}{'full':>12}{'common':>12}{'teams':>9}", "-" * 47]
    order = sorted(results["common"], key=lambda k: -abs(results["common"][k][0]))
    for label in order:
        f_r, _ = results["full"][label]
        c_r, n = results["common"][label]
        lines.append(f"{label:<14}{f_r:>12.3f}{c_r:>12.3f}{n:>9}")
    lines += [
        "",
        f"Correlation with {E} team win percentage. All arms frozen on "
        f"{a.train_lo}-{a.train_hi}.",
        "'common' restricts to players rated by every arm and is the comparable column.",
        "",
        "Compare against the in-window figures from team_agg_corr.py. A large fall",
        "for rapm relative to the box-score arms supports the reading that its",
        "in-window team-level signal is fitted rather than transferable.",
    ]
    print("\n".join(lines))

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines) + "\n")
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
