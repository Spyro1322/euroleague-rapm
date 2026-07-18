#!/usr/bin/env python3
"""
scripts/build_league_averages.py  —  Week 3, luck-adjustment support.

Per-SEASON league 3-point percentage, for the RAPM luck adjustment. Per-season
(not pooled) because Euroleague 3P volume and accuracy drift across 2007-2026;
a single pooled mean would misattribute 3-point luck by era.

FGA reconstruction (validated against the full feed: 3P%=36.17%, 2P%=52.96%):
    3PA = 3FGM + 3FGA + 3FGAB        (made + missed + blocked)

Output:
    warehouse/league_averages.parquet   Season, lg_3pm, lg_3pa, lg_3p_pct

Run before rebuilding the stint matrix with luck adjustment.
"""
from __future__ import annotations
import logging
from pathlib import Path

import polars as pl

LOG = logging.getLogger("league_avg")
PBP_GLOB = "data/pbp_lineups/**/*.parquet"
OUT = Path("warehouse/league_averages.parquet")

MADE_3 = {"3FGM"}
ATT_3 = {"3FGM", "3FGA", "3FGAB"}   # all 3-point ATTEMPTS


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    lf = pl.scan_parquet(PBP_GLOB)
    agg = (
        lf.select("Season", "PLAYTYPE")
        .with_columns(
            pl.col("PLAYTYPE").is_in(list(MADE_3)).alias("is_3pm"),
            pl.col("PLAYTYPE").is_in(list(ATT_3)).alias("is_3pa"),
        )
        .group_by("Season")
        .agg(pl.col("is_3pm").sum().alias("lg_3pm"),
             pl.col("is_3pa").sum().alias("lg_3pa"))
        .with_columns((pl.col("lg_3pm") / pl.col("lg_3pa")).alias("lg_3p_pct"))
        .sort("Season")
        .collect()
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    agg.write_parquet(OUT)
    with pl.Config(tbl_rows=25):
        LOG.info("per-season league 3P%%:\n%s", agg)
    LOG.info("pooled check: %.2f%% (expect ~36.2)",
             100 * agg["lg_3pm"].sum() / agg["lg_3pa"].sum())
    LOG.info("wrote %s", OUT)


if __name__ == "__main__":
    main()
