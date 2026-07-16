# Thesis Status — Euroleague Shot-Context RAPM + Lineup Synergy

_Last updated: end of Week 3_  ·  _Submission target: start of August 2026_

## Current phase
- Week 3 closing → Week 4 next (Streamlit Tab 1 + GitHub Actions refresh).
- **BLOCKING DECISION before Week 4 starts:** pooled-career vs 5-season rolling window (see Open issues). Bootstrap and Tab 1 both depend on it.

## Done
- Thesis proposal (5 sections, approved by supervisor).
- 11-week timeline.
- **Week 1 — lineup validation (CLOSED):** repo skeleton, Docker, pyproject; euroleague_api pinned 0.1.1; 10-on-court via get_game_pbp_data_lineups(validate=True). Full-range validation: 95 games, 48,827 actions (docs/wk1_validation.md).
  - CAVEAT: Week 1 validated the data but never **persisted** a warehouse. The real O1 ingest happened in Week 2.
- **Week 2 — ETL persistence + stint matrix + play-context tagger (CLOSED):**
  - **Ingest:** full 2007-08 → 2025-26 PBP → canonical Parquet (`data/pbp_lineups/`). 5,039 of 5,040 played games; 2018 gc21 has no PBP in the feed. `scripts/ingest_pbp.py`, resume-safe.
  - **Warehouse:** `sql/schema.sql`; `pbp_lineups` is a VIEW over Parquet. 2,603,015 rows. `scripts/build_warehouse.py`.
  - **Stint matrix:** `warehouse/stints.parquet` — 279,174 stints, 375,612 team-possessions (74.5/team/game). `scripts/build_stint_matrix.py`.
  - **Shot feed:** `scripts/ingest_shots.py` — 2023 ingested (50,159 shots). Full range still TO PULL (Week 6).
  - **Play-context tagger:** `scripts/play_context.py` (6 outcome-independent buckets), `scripts/tag_shots.py` (join-match 99.95%). 2023: 41,331 FGAs.
  - Appendix figure: `fig_play_context_decision_tree.svg`.
- **Week 3 — player ID map + baseline ridge RAPM + Olivo replication (CLOSED bar luck adjustment):**
  - **Boxscore ingest:** `scripts/ingest_boxscore.py` — REWRITTEN (see bug #4). Per-game shards under `landing/boxscore_players/season=YYYY/game_NNNNN.parquet`, own 429 backoff, per-season `_SUCCESS` / `_MISSING.csv` completeness gate. All seasons complete except 2018 gc21 — **the same game missing from the PBP feed, independently detected by two ingests.**
  - **ID map (the blocker):** `scripts/build_player_id_map.py` + `config/id_merges.csv` + `scripts/triage_id_collisions.py`.
    - `warehouse/player_id_map.parquet` — 6,413 (name, season) rows → 2,374 distinct players.
    - `warehouse/stints_ids.parquet` — 279,174 stints, lineups as PLAYER_ID lists. No rows lost.
    - `warehouse/tagged_shots_ids.parquet` — shooter + `off_players`/`def_players` remapped. 35/41,311 shooters unmapped (0.08%) — Week 6 item, off the O2 path.
  - **Design matrix:** `scripts/build_rapm_design.py` — 296,683 observations, 2,183 players → 4,366 columns, X strictly 0/1, mean y = 105.89/100, 751,146 possessions, 5,039 CV groups.
  - **Baseline fit:** `scripts/fit_ridge_rapm.py` — α=3162.3 (interior, U-shaped CV curve), 1,478 players ≥500 poss. RAPM mean 0.09, sd 1.60, min −4.84, max +8.17. `warehouse/rapm_baseline.{parquet,csv}`.
  - **Olivo replication (PASSED):** like-for-like refit on his window via `--seasons 2018:2022 --prefix rapm_olivo --min-games 50`. 84,053 stints, 657 players, 1,466 games, 240 players after ≥50-games filter.

## Olivo (2024) replication — result
Francesco Olivo, _Advanced Basketball Analytics_, MSc Artificial Intelligence, Università di Bologna. Supervisor C. Sartori, co-supervisor **Sergio Scariolo**. AMS Laurea eprint 30803. **Title page says "Fifth Session, Academic Year 2022-23" — VERIFY the 2024 date on the repository record before citing.**

His protocol: ridge, 5-fold CV, **2018-19 → 2022-23 pooled**, **≥50 games**, λ=354.5 (glmnet). Conventions identical to ours (higher DRAPM = better defence; RAPM = ORAPM + DRAPM; two rows per stint, one per offensive team).

| check | result |
|---|---|
| his top 10 | **10/10** inside our top 34 of 240; 8 inside our top 15 |
| his bottom 5 | **5/5** match ours (Radosevic, Enoch, Eric, Schneider, Nnoko) |
| RAPM sd | 1.77 (ours) vs 1.52 (his) |
| Canaan ORAPM/DRAPM/RAPM | 0.06 / 2.35 / **2.41** vs his 0.15 / 2.25 / **2.4** |
| Balbay | −0.06 / 2.41 / **2.36** vs his 0.66 / 1.87 / **2.53** |
| Tavares | 3.19 / 4.73 / **7.92** vs his 0.76 / 2.17 / **2.93** |

**Interpretation (for Ch4):** ordering replicates; agreement is near-exact for prior-dominated (low-possession) players and diverges with possession count. λ values are **NOT comparable** — glmnet minimises `(1/2n)·RSS + (λ/2)‖β‖²` with standardised predictors, sklearn minimises `RSS + α‖β‖²` on raw 0/1 columns. Olivo also adds game-context weights (playoff ×2, clutch ×2, garbage ×0.5) we do not. Residual difference concentrates in high-possession players, consistent with a weaker effective penalty in our fit. Do not claim a clean numeric match; claim rank replication + a diagnosed scale difference.

## In progress
- (none open) — Week 3 closed bar luck adjustment.

## Key decisions made
- Season range: full 2007-08 → 2025-26, no truncation (validated).
- euroleague_api pinned 0.1.1; lineups via get_game_pbp_data_lineups(validate=True).
- **Taxonomy LOCKED — 6 shot-context buckets** (transition, second_chance, at_rim, mid_range, corner_three, above_break_three). "Assisted" dropped (confounds context with outcome).
- Turnovers AND free throws not tagged; both remain in baseline RAPM.
- Parquet canonical; DuckDB views over it; .duckdb + warehouse/ + data/ gitignored.
- **RAPM design:** two observations per stint (one per offensive team); y = points/100 poss; row weight = offensive possessions; columns `off_<id>` / `def_<id>`. **ORAPM = off coef; DRAPM = −(def coef) so positive = good; RAPM = ORAPM + DRAPM.** Matches Olivo.
- **Player ID map keyed on (name, season), NOT name.** Lineups are name-strings (the euroleague_api walker tracks names, not IDs), so a map is unavoidable. Name-only keys are unsafe — see ID findings. Hard-asserted: every (name, season) → exactly one id, else exit 3.
- **9 curated ID merges in `config/id_merges.csv`** — record of decision, hand-verified, not auto-generated.
- **CV/bootstrap group key = (Season, Gamecode)**, never Gamecode alone.

## Player ID findings (Ch3 methodology + Ch9 limitation)
- The feed carries **at least four ID schemes** across 2007–2026: legacy short codes (`PKSF`, `PTHY`, `PLRU`), team-scoped legacy (`MAD991`, `LJU1`, `PSIE374368`), modern canonical (`P######`), and junk (`1`).
- 10 name-strings map to >1 PLAYER_ID. **9 are one player under two ids** (format artifact, team-scoped legacy, one-char typo, junk id, duplicate registration) → merged.
- **1 is a true homonym: SIMONOVIC, MARKO.**
  - `PLRU` = b. 30 May 1986, Serbian, 2.03m SF. EuroLeague profile code `lru`. Crvena Zvezda 2013-14…2021-22, retired 2022.
  - `P012711` = b. 15 Oct 1999, Montenegrin, 2.13m C. EuroLeague profile code `012711`. Crvena Zvezda 2023-24 only, then Beşiktaş.
  - Verified against official EuroLeague profile URLs. **They must not be merged.**
  - The structural triage heuristic proposed MERGE_DISJOINT for this case — **the automated verdict was wrong on the only case that mattered.** Their footprints look disjoint solely because one retired as the other arrived at the same club. Overridden by `config/id_merges.csv`.
- Boxscore backstop adds **341 (name, season) combos unseen in the PBP feed** — players who logged court time but never recorded a PBP action with an ID. The backstop is load-bearing, not insurance.

## euroleague_api 0.1.1 bugs worked around (Ch9 / reproducibility)
1. **IsHomeTeam** is None for every row of any game whose feed pads team codes. Home/away derived from **Lineup_A membership**.
2. **Substitution matcher** mis-pairs simultaneous subs → duplicated-player fives. See correction below.
3. **FT mis-tagged as transition** via FASTBREAK/SECOND_CHANCE flags → FG-attempt guard in `tag_shots.py`.
4. **NEW — season wrappers silently drop failed games.** `utils.get_data_over_collection_of_games` catches `HTTPError` per game, logs "Skip and continue", and **never re-raises**. No retry, no backoff. A season rate-limited (HTTP 429) into 90% failures returns a DataFrame indistinguishable from a complete one. `get_players_boxscore_stats_single_season` is therefore **unsafe for full-range pulls**. Worked around by driving the per-game endpoint directly with our own backoff + a per-season completeness gate.
5. **NEW (data, not library) — `Gamecode` is season-scoped.** Only **402 distinct values across 5,039 games**. Any group/join/CV keyed on Gamecode alone silently merges ~19 unrelated games. Use (Season, Gamecode).

## Corrections to earlier claims
- **Week 2 STATUS said 27 duplicated-five games were "excluded via `lineup_ok` guard". They were not.** `lineup_ok` is `true` for all 279,174 rows of `stints.parquet` — the flag never propagated. 33 stints across **2 games** still carried duplicated fives. `build_stint_matrix.py` evidently excluded most of the 27, but the flag records nothing and 2 games leaked.
  - Consequence had it gone unnoticed: `scipy.coo_matrix` **sums** duplicate (row, col) pairs, so a repeated player becomes a **2.0** in the design matrix — counted as two men on the floor. Silent, not an error.
  - Fixed: distinctness is **re-derived** in `build_rapm_design.py` (`ENFORCE_DISTINCT_FIVES`), plus a hard assert that X is strictly 0/1. Post-fix nnz shortfall = 0.
  - TODO: either fix `build_stint_matrix.py` to populate `lineup_ok` properly, or delete the column. Right now it is decorative and anything trusting it inherits the bug.

## Open issues / watch
- **DECIDE BEFORE WEEK 4 — pooled-career vs rolling window.** Current design gives each player ONE coefficient across all 19 seasons (Mirotic 2008→2025 = one number spanning a 17-y/o prospect and a 34-y/o star). Two consequences:
  1. **Ch7's held-out 2025-26 evaluation currently leaks** — `last_season = 2025` means the hold-out is inside the training design.
  2. **O5's weekly refresh implies current-form ratings**, not career averages.
  - Olivo's precedent is a **5-season pooled window**, not a career pool — he argues RAPM needs multiple seasons but does not pool a whole career.
  - Options: (a) 5-season rolling windows (cheap — `--seasons` flag already exists; citable; fixes the leak); (b) player-season columns with shrinkage toward a career mean (~12.8k columns; more principled, more work, risks O3/O4 time).
- **Luck adjustment NOT DONE.** `stints.parquet` has no expected-points columns, so `build_rapm_design.py` fits on raw points (`HOME_XPTS_COL`/`AWAY_XPTS_COL` = None). Either revisit the Week-2 possession walker to emit expected points (3P makes → 3·3PA·leagueAvg3P%), or state in Ch4 that the baseline is unadjusted and why. **This is the one Week-3 scope item still open.**
- **λ is weakly identified.** CV picked α=3162.3 for BOTH the 297k-obs and 87k-obs fits — the same grid point on a third of the data. The curve is flat near the optimum (5110.53 @ 3162 vs 5110.98 @ 1995 = 0.01%) and the 16-point grid is coarse (~0.2 dex). "CV-selected λ" is doing less work than the phrase implies. Say so in Ch4.
- **Bootstrap not run.** Run ONCE, after the design decision, before Tab 1 (Tab 1 + Ch4 both need RAPM_lo/RAPM_hi).
- 35/41,311 unmapped shooters (0.08%) in tagged_shots — Week 6 / O3.
- `transition` rate ~4.7% — describe as "feed-flagged fastbreak", don't over-claim.
- SCOPE (decide before Wk6): O4 lineup-pair synergy (proposal, PyMC, Wk8) vs similarity-finder (timeline). Design extends cleanly to pair columns.

## Citations to verify (before submission)
- **Olivo** — title page says AY 2022-23, Fifth Session; bibliography says 2024. Check the AMS Laurea record.
- **Grassetti** — Olivo cites it as **2019** ("Estimation of lineup efficiency effects in basketball using play-by-play data", Grassetti, Bellio, Fonseca, Vidoni), our Ch2 says 2021. Possibly a preprint vs journal version. Resolve.
- Ch2 free positioning: Olivo criticises Grassetti's weighting as arbitrary — biased toward what the author believes matters (made/missed shots) rather than objective efficiency per 100 possessions. **This is a ready-made argument for our outcome-independent buckets** (the "assisted axis dropped" reasoning).
- Novelty confirmed: Olivo does ridge/lasso/elastic-net, BPM fine-tuning, multi-league RAPM. **No play-type conditioning, no lineup-pair synergy.** O3 and O4 unclaimed.
- Still flagged from Wk2: lasso-multinomial authorship, Win Score/Berri.

## Next actions (Week 4)
1. **Decide pooled vs rolling window** (blocks 2 and 3).
2. **Run bootstrap ONCE** on the committed design → RAPM_lo/RAPM_hi.
3. Streamlit Tab 1 (leaderboard, O/D split, CIs) + GitHub Actions weekly refresh.
4. Ch2 Olivo stub → real text; Ch4 baseline draft (writing chat).
5. Background job anytime: `ingest_shots.py --seasons 2007-2025` (Week 6 / O3) — **run solo**, the API rate-limits (429) under concurrent pulls.

## Links
- GitHub repo: https://github.com/Spyro1322/euroleague-rapm
- HF Space URL: (pending Wk5)
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Current artifacts: warehouse/{stints_ids, tagged_shots_ids, player_id_map, rapm_design, rapm_players, rapm_baseline, rapm_olivo_baseline}
- Decision records: config/id_merges.csv, reports/id_collision_triage.csv