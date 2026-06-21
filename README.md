# Euroleague Play-Type RAPM + Lineup-Pair Synergy

MSc thesis (UCAM — AI Applied to Sports). Play-type-conditional and
lineup-pair-synergy RAPM for the Euroleague, seasons 2007-08 → 2025-26.

## Objectives
- **O1** Reproducible ETL: possession-level lineups + play-type tags.
- **O2** Baseline ridge RAPM with luck adjustment.
- **O3** Play-type-conditional RAPM (PnR handler/roller, iso, spot-up, post-up, transition, off-screen).
- **O4** Lineup-pair synergy with opponent-strength adjustment + credible intervals.
- **O5** Public Streamlit dashboard on Hugging Face Spaces, weekly auto-refresh.

## Stack
Python · `euroleague_api 0.1.1` · DuckDB + Polars + Parquet · scikit-learn ·
NumPy/SciPy · statsmodels · PyMC + ArviZ · Streamlit + Plotly · Docker · GitHub Actions.

## Week 1 — do this first
The 10-on-court reconstruction is the load-bearing assumption of the whole
thesis. `euroleague_api` builds it from boxscore `IsStarter` + PBP `IN`/`OUT`
events, and it is known to degrade in older seasons. Before anything else,
measure it:

```bash
pip install -e .
make schema          # build DuckDB from sql/schema.sql
make validate-quick  # smoke test on 2023-2025
make validate        # full 2007-2025 sweep -> data/validation/*.parquet
```

`scripts/validate_lineups.py` reports, per season: `games_ok`, `boxscore_ok`,
`valid_rate`, `five_invariant`, `empty_lineup_rate`. **Decision rule:** the
earliest season where `valid_rate` and `five_invariant` are both stable and
≥ ~0.97 is the real start of the usable range. Record it in `STATUS.md` — it
resolves the season-range scope question and feeds the ch.3 validation table
(the 20 poss × 5 games protocol is the manual companion to this automated sweep).

## Layout
```
sql/schema.sql              DuckDB schema (landing + warehouse)
scripts/validate_lineups.py Week-1 lineup-quality sweep
src/elrapm/config.py        season range + paths
src/elrapm/ingest/          season -> landing parquet
src/elrapm/etl/             stint matrix (Week 2)
data/                       parquet artifacts (gitignored)
```
