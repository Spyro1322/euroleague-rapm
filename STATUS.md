# Thesis Status — Euroleague Play-Type RAPM + Lineup Synergy

_Last updated: 2026-06-21_  ·  _Submission target: start of August 2026_

## Current phase
- Week 0 — project setup (Claude Project + repo not yet created)

- Week 1 complete → starting Week 2 (stint matrix + play-type tagger)

## Done
- Thesis proposal written (5 sections, approved YES by supervisor)
- 10-week timeline drafted
- Week 1 — repo + API setup + lineup validation (CLOSED): GitHub repo skeleton, DuckDB schema, Docker, pyproject stood up. euroleague_api pinned 0.1.1; 10-on-court lineups via PlayByPlay.get_game_pbp_data_lineups(validate=True).
    Full-range validation (95 games, 48,827 actions): see docs/wk1_validation.md.

## In progress
- Week 2: possession-level stint matrix + 7-type play-type tagger.

## Blocked / open issues
- SCOPE: proposal promises lineup-pair synergy (O4); timeline has a play-type *similarity finder* in Wk 8 instead. Decide which is in scope before Week 6. (See decisions log.)
- euroleague_api v0.1.0 not yet validated against full season range →
    RESOLVED: full 2007-08 → 2025-26 validated, no truncation
    (docs/wk1_validation.md).

## Key decisions made
- Season range: full 2007-08 → 2025-26, no truncation (validated).
- euroleague_api pinned 0.1.1; lineups via get_game_pbp_data_lineups(validate=True).
- Residual on-court mis-attribution 0.12% (team events excluded via pbp_clean); no sub-timing correction — magnitude doesn't justify it.

## Next 3 actions
1. Build possession-level stint matrix from warehouse.pbp_clean across all seasons.
2. Write the 7-type play-type tagger from PBP event sequences.
3. Manual tagger validation: 20 possessions × 5 games vs official PBP.

## Links
- GitHub repo: https://github.com/Spyro1322/euroleague-rapm
- HF Space URL:
- Current leaderboard CSV/Parquet:
