# Thesis Status — Euroleague Play-Type RAPM + Lineup Synergy

_Last updated: end of Week 2_  ·  _Submission target: start of August 2026_

## Current phase
- Week 2 closing → Week 3 next (ridge RAPM baseline / design matrix).

## Done
- Thesis proposal (5 sections, approved by supervisor).
- 11-week timeline.
- **Week 1 — lineup validation (CLOSED):** repo skeleton, Docker, pyproject; euroleague_api pinned 0.1.1; 10-on-court via get_game_pbp_data_lineups(validate=True). Full-range validation: 95 games, 48,827 actions (docs/wk1_validation.md).
  - CAVEAT discovered in Wk2: Week 1 validated the data but never **persisted** a warehouse — no .duckdb, only validation summaries on disk. The real O1 ingest happened in Week 2.
- **Week 2 — ETL persistence + stint matrix + play-context tagger (CLOSED bar manual eyeball):**
  - **Ingest:** full 2007-08 → 2025-26 PBP persisted to canonical Parquet (`data/pbp_lineups/`). 5,039 of 5,040 played games; 2018 gc21 has no PBP in the feed (excluded, immaterial). `scripts/ingest_pbp.py`, resume-safe.
  - **Warehouse:** `sql/schema.sql` reconciled — `pbp_lineups` is a VIEW over Parquet; `pbp_clean` (distinctness) and `pbp_poss` (possession-complete) fixed. Built by `scripts/build_warehouse.py` (schema-of-record). 2,603,015 rows.
  - **Lineup-composition QC:** `scripts/qc_lineups.py` — 27 of 5,039 games (0.54%) carry duplicated-player fives (sub-matcher cascade); excluded via `lineup_ok` guard.
  - **Stint matrix:** `warehouse/stints.parquet` — 279,174 stints, 375,612 team-possessions (74.5/team/game, 149 total — correct Euroleague pace), 55.4 stints/game. `scripts/build_stint_matrix.py`.
  - **Shot feed:** `scripts/ingest_shots.py` — 2023 ingested (50,159 shots, 99.2% with coords). Full range still TO PULL.
  - **Play-context tagger:** `scripts/play_context.py` (6 outcome-independent buckets), `scripts/tag_shots.py` (join-match-rate 99.95% — NUM_ANOT↔NUMBEROFPLAY confirmed). FG-attempt guard added after manual eyeball caught free throws (FTM) being mis-tagged via the FASTBREAK/SECOND_CHANCE flags. 2023: 50,159 Points-feed rows → 41,331 FGAs (8,828 FTs/non-shots excluded). Bucket mix passes priors (above-break 33.1%, at_rim 26.9%, mid 23.4%, second-chance 6.6%, corner 5.2%, transition 4.7%).
  - **Validation harness:** `scripts/validate_tagging.py` — coords confirm SIDELINE_AXIS + corner thresholds (corner = 13.5% of threes; spot-checked: all corner_three at |X|∈[664,702], Y∈[-62,194], both corners). Manual 20×5 eyeball done.
  - Appendix figure: `fig_play_context_decision_tree.svg`.

## In progress
- (none open) — Week 2 closed.

## Key decisions made
- Season range: full 2007-08 → 2025-26, no truncation (validated).
- euroleague_api pinned 0.1.1; lineups via get_game_pbp_data_lineups(validate=True).
- **Taxonomy LOCKED — 6 shot-context buckets** (transition, second_chance, at_rim, mid_range, corner_three, above_break_three). Chapter 5 reframed: "play-type" → **shot-context-conditional RAPM**. Assisted dropped as an axis (only exists on makes → would confound context with outcome); kept as a descriptive overlay.
- Turnovers AND free throws not tagged; both remain in baseline RAPM. FTA/FTM are non-FGA Points-feed rows — only field-goal attempts get a bucket. (FT points still counted in stints.parquet via the possession walker.)
- Parquet canonical; DuckDB views over it; .duckdb + warehouse/ + data/ all gitignored (regenerable).

## euroleague_api 0.1.1 bugs worked around (note for Ch9 / reproducibility)
- **IsHomeTeam** is None for every row of any game whose feed pads team codes (stripped CODETEAM vs unstripped CodeTeamA). Home/away derived from **Lineup_A membership** instead.
- **Substitution matcher** mis-pairs simultaneous subs in 0.54% of games → duplicated-player fives. Guarded by `lineup_ok` distinctness (not `len()==5`).
- `five_invariant` redefined: distinctness, not cardinality.

## Next 3 actions (Week 3)
1. **FIRST — name→ID mapping (blocks everything):** ingest boxscore (`get_players_boxscore_stats` → `landing.boxscore_players`) for the name↔PLAYER_ID map; remap lineups in stints.parquet (and tagged_shots) from NAMES to canonical PLAYER_ID. Diacritics/collisions will corrupt ridge columns otherwise.
2. Build the ridge RAPM design matrix from `stints.parquet` (on IDs); CV λ; luck adjustment.
3. Replicate Olivo (2024) headline numbers as sanity check; export baseline leaderboard.

_Not on the Week-3 critical path: full-range shot ingest (`ingest_shots.py --seasons 2007-2025`) is for Week 6 (O3); pull it as a background job anytime. O2 baseline needs only stints.parquet._

## Open issues / watch
- `transition` rate ~4.7% (feed FASTBREAK is conservative — describe as "feed-flagged fastbreak", don't over-claim).
- SCOPE (decide before Wk6): proposal promises lineup-pair synergy (O4, PyMC, Wk8); timeline has a similarity-finder there instead. Design the Wk3 matrix to extend cleanly to pairs if O4 stays in.
- Week 2 ran well past its 14–18h budget (absorbed the un-persisted Wk1 ingest). Weeks 6–8 unchanged; protect Week 8 slack.

## Links
- GitHub repo: https://github.com/Spyro1322/euroleague-rapm
- HF Space URL: (pending Wk5)
- Current artifacts: warehouse/stints.parquet, warehouse/tagged_shots_2023.parquet