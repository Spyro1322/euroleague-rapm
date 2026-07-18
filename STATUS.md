# Thesis Status — Euroleague Shot-Context RAPM + Lineup Synergy

_Last updated: end of Week 4_  ·  _Submission target: start of August 2026_

## Current phase
- Week 4 **fully closed** (windowing decision + three fits + bootstrap CIs + dashboard Tab 1, all validated) → Week 5 next (**deploy to HF Spaces; MVT checkpoint — thesis passes from here**).
- Pooled-career vs rolling-window decision RESOLVED (see Key decisions). No open blockers into Week 5.

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
- **Week 3 — player ID map + baseline ridge RAPM + Olivo replication + luck adjustment (CLOSED):**
  - **Boxscore ingest:** `scripts/ingest_boxscore.py` — REWRITTEN (see bug #4). Per-game shards under `landing/boxscore_players/season=YYYY/game_NNNNN.parquet`, own 429 backoff, per-season `_SUCCESS` / `_MISSING.csv` completeness gate. All seasons complete except 2018 gc21 — **the same game missing from the PBP feed, independently detected by two ingests.**
  - **ID map (the blocker):** `scripts/build_player_id_map.py` + `config/id_merges.csv` + `scripts/triage_id_collisions.py`.
    - `warehouse/player_id_map.parquet` — 6,413 (name, season) rows → 2,374 distinct players.
    - `warehouse/stints_ids.parquet` — 279,174 stints, lineups as PLAYER_ID lists. No rows lost.
    - `warehouse/tagged_shots_ids.parquet` — shooter + `off_players`/`def_players` remapped. 35/41,311 shooters unmapped (0.08%) — Week 6 item, off the O2 path.
  - **Design matrix:** `scripts/build_rapm_design.py` — 296,683 observations, 2,183 players → 4,366 columns, X strictly 0/1, 751,146 possessions, 5,039 CV groups. Luck-adjusted target: mean y = 105.51/100 (raw was 105.89).
  - **Baseline fit (luck-adjusted):** `scripts/fit_ridge_rapm.py` — α=1995.3 (interior, U-shaped CV; dropped from 3162 raw because the adjusted target is less noisy). 1,478 players ≥500 poss. RAPM mean 0.10, sd 1.62, min −5.26, max +7.65. `warehouse/rapm_baseline.{parquet,csv}`.
  - **Luck adjustment (DONE):** per-season league 3P% via `scripts/build_league_averages.py`; 3-pt makes replaced by expected (3PA × season league 3P%), 2s and FTs left realised. Walker emits `home_xpts`/`away_xpts`; design `HOME_XPTS_COL`/`AWAY_XPTS_COL` wired on. Validated: realised 796,713 pts vs expected 796,714 (diff +0.000%). Effect is subtle and correct — rim-runners (Tavares ORAPM 3.60→2.36) shed teammates' 3-pt variance, defence signal sharpens (Tavares DRAPM 4.57→5.29); perimeter scorers whose offence isn't 3-variance-driven (Thompson ORAPM 4.13) survive adjustment.
  - **Olivo replication (PASSED):** like-for-like refit on his window via `--seasons 2018:2022 --prefix rapm_olivo --min-games 50`. 84,053 stints, 657 players, 1,466 games, 240 players after ≥50-games filter.
- **Week 4 — windowing decision + three fits + bootstrap CIs + dashboard Tab 1 (CLOSED, all validated):**
  - **Windowing decision (RESOLVED):** 5-season rolling windows, three fits, start-year convention. Rejected the career pool (leaks 2025-26 into Ch7; "current form" ill-defined over a 17-season span) and player-season columns (~12.8k cols, robs O3/O4 time — logged as future work). Matches Olivo's 5-season precedent → citable.
    - `rapm_baseline` — all-time 2007:2025, career/historical leaderboard (Ch4).
    - `rapm_eval` — 2020:2024, Ch7 hold-out fit (2025-26 excluded → no leak).
    - `rapm_dash` — 2021:2025, current-form dashboard fit (Tab 1, O5 weekly refresh). Eval is the dash window lagged one season, so Ch7 scores the deployed rating on a season it never saw.
  - **Bootstrap CIs (DONE — via `fit_ridge_rapm.py --bootstrap`, NOT the Week-3 standalone plan):** game-level cluster bootstrap on (Season, Gamecode), B=500, refit at fixed α. Emits RAPM_lo/RAPM_hi.
    - `rapm_baseline`: α **pinned 1995.3** to reproduce the validated Week-3 fit. Ran to scratch `rapm_baseline_ci`, diffed vs `rapm_baseline` (max |ΔRAPM|=6.4e-5, |ΔORAPM|=4.5e-5, |ΔDRAPM|=4.6e-5 — f32 solver dust at tol=1e-4, ~the measurement floor), then promoted. `rapm_baseline.parquet` now carries RAPM_lo/RAPM_hi.
    - `rapm_dash`: CV-selected α **3162.3** (interior, U-shaped: 1995.3→3038.97, 3162.3→3038.55, 5011.9→3038.92). 517 players ≥500 poss; RAPM mean 0.04, sd 1.20, min −3.24, max 4.90. Face-valid (Tavares #1 on defence). **All top-15 RAPM_lo>0 and all bottom-5 RAPM_hi<0** — extremes reliably separated from average.
  - **Evaluation fit (DONE, hold-out VERIFIED):** `rapm_eval`, CV α 3162.3, 495 players ≥500 poss; RAPM mean 0.05, sd 1.18, min −3.31, max 5.51. No bootstrap (Ch7 uses point estimates + RMSE). **Hold-out verified directly on the design, not trusted from the flag:** `rapm_eval_design.npz` `groups` is an int64 key `SSSSGGGGG` (season high digits, gamecode low 5); `groups // 100000` → season range **2020 → 2024, 5 seasons, 1,616 games**. No 2025 prefix present ⇒ 2025-26 is fully out of training. Player count (495) is window-consistent with dash (517) and nowhere near all-time (1,478), a second confirmation the `--seasons` flag took.
  - **Dashboard Tab 1 (`app/streamlit_app.py`):** tabbed shell, Tab 1 live (leaderboard, O/D split, RAPM 95% CI, current/all-time toggle, `--min-poss 3000` display filter, search). Renders pre-computed parquet only (no live training). Tabs 2-5 stubbed (Wk6/8/9). `DATA_DIR` honours `RAPM_WAREHOUSE` env (for `app/` subfolder layout + HF Spaces). "Career span" column is the dataset-wide span, explicitly NOT the rating window. `width="stretch"` (post-deprecation `use_container_width`).
  - **GitHub Actions (`.github/workflows/refresh.yml`):** weekly refresh of the dashboard window only (design→fit→bootstrap→commit `rapm_dash.parquet`). `DASH_ALPHA=3162.3` pinned so the cron doesn't re-CV onto a neighbouring flat-curve grid point. **Staged, not wired — HF push is a Week-5 stub; do not debug cron until the Space exists.**

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
- (none open) — Week 4 fully closed.

## Key decisions made
- Season range: full 2007-08 → 2025-26, no truncation (validated).
- euroleague_api pinned 0.1.1; lineups via get_game_pbp_data_lineups(validate=True).
- **Taxonomy LOCKED — 6 shot-context buckets** (transition, second_chance, at_rim, mid_range, corner_three, above_break_three). "Assisted" dropped (confounds context with outcome).
- Turnovers AND free throws not tagged; both remain in baseline RAPM.
- Parquet canonical; DuckDB views over it; .duckdb + warehouse/ + data/ gitignored.
- **RAPM design:** two observations per stint (one per offensive team); y = points/100 poss; row weight = offensive possessions; columns `off_<id>` / `def_<id>`. **ORAPM = off coef; DRAPM = −(def coef) so positive = good; RAPM = ORAPM + DRAPM.** Matches Olivo.
- **Player ID map keyed on (name, season), NOT name.** Lineups are name-strings (the euroleague_api walker tracks names, not IDs), so a map is unavoidable. Name-only keys are unsafe — see ID findings. Hard-asserted: every (name, season) → exactly one id, else exit 3.
- **9 curated ID merges in `config/id_merges.csv`** — record of decision, hand-verified, not auto-generated.
- **CV/bootstrap group key = (Season, Gamecode)**, never Gamecode alone. Persisted as an int64 encoding `SSSSGGGGG` in the design npz's `groups` array (season = `groups // 100000`).
- **Windowing (Wk4): 5-season rolling, three fits** — `rapm_baseline` 2007:2025 (all-time historical), `rapm_eval` 2020:2024 (hold-out-safe), `rapm_dash` 2021:2025 (current/dashboard). Career pool retained only as a free historical leaderboard, not a "current" rating.
- **Bootstrap = built-in `--bootstrap` flag**, not the standalone script. Game-level cluster bootstrap, fixed α, B=500. Produces RAPM_lo/RAPM_hi only (no O/D bands — fine for a ranked leaderboard; ~4-line add in `bootstrap_ci` if wanted later).
- **Committed α per fit:** rapm_baseline **1995.3** (pinned), rapm_dash **3162.3** (CV), rapm_eval **3162.3** (CV). All three land within one coarse-grid point on flat CV curves (~0.01–0.02% wMSE spread) — a live instance of the "λ weakly identified" caveat, not a real disagreement. Weekly cron pins `DASH_ALPHA=3162.3`.

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
4. **season wrappers silently drop failed games.** `utils.get_data_over_collection_of_games` catches `HTTPError` per game, logs "Skip and continue", and **never re-raises**. No retry, no backoff. A season rate-limited (HTTP 429) into 90% failures returns a DataFrame indistinguishable from a complete one. `get_players_boxscore_stats_single_season` is therefore **unsafe for full-range pulls**. Worked around by driving the per-game endpoint directly with our own backoff + a per-season completeness gate.
5. **(data, not library) — `Gamecode` is season-scoped.** Only **402 distinct values across 5,039 games**. Any group/join/CV keyed on Gamecode alone silently merges ~19 unrelated games. Use (Season, Gamecode).

## Corrections to earlier claims
- **Week 2 STATUS said 27 duplicated-five games were "excluded via `lineup_ok` guard".** Investigated in Week 3: the flag never propagated to the on-disk `stints.parquet` (all rows `true`, yet 33 stints across 2 games still carried duplicated fives). **RESOLVED:** `stints.parquet` was rebuilt end-of-Week-3 from `warehouse/pbp_poss.parquet` with the current `build_stint_matrix.py` (drop_corrupt=True fired), so the artifact now matches the code and `lineup_ok` is meaningful. The design build also re-derives distinctness (`ENFORCE_DISTINCT_FIVES`) with a hard 0/1 assert as belt-and-braces. `scipy.coo_matrix` would otherwise SUM a duplicated player into a 2.0 (two men on the floor) — silent, not an error.
  - Provenance note: the rebuilt `stints.parquet` still shows 33 dup-five stints pre-filter at the design stage because the design guard runs on `stints_ids.parquet` before the drop; net effect on the model is zero (dropped). If revisiting, decide whether `build_stint_matrix.py`'s drop should happen before or after the ID remap.

## Open issues / watch
- **Display filter for Ch4 leaderboard.** Model uses `--min-poss 500`, but the presented top-15 lets low-sample players climb. For the *presented* table use `--min-poss 3000`; keep 500 for the model itself. Tab 1 already defaults to 3000 for display; low-sample climbers (e.g. Morgan single-2025-season, Webb III 2-season) recede in the dashboard view. Filter for display, not for fitting.
- **λ is weakly identified.** All three Wk4 fits landed within one grid point (rapm_baseline 1995.3; dash + eval 3162.3) on curves flat to ~0.01–0.02% near the optimum; the 16-point logspace grid is coarse (~0.2 dex). "CV-selected λ" is doing less work than the phrase implies. Say so in Ch4.
- 35/41,311 unmapped shooters (0.08%) in tagged_shots — Week 6 / O3.
- `transition` rate ~4.7% — describe as "feed-flagged fastbreak", don't over-claim.
- Bootstrap produces RAPM CIs only, not O/D. Fine for the leaderboard; add ORAPM/DRAPM percentiles in `bootstrap_ci` (~4 lines) if a later chapter needs O/D bands.
- SCOPE (decide before Wk6): O4 lineup-pair synergy (proposal, PyMC, Wk8) vs similarity-finder (timeline). Design extends cleanly to pair columns.

## Citations to verify (before submission)
- **Olivo** — title page says AY 2022-23, Fifth Session; bibliography says 2024. Check the AMS Laurea record.
- **Grassetti** — Olivo cites it as **2019** ("Estimation of lineup efficiency effects in basketball using play-by-play data", Grassetti, Bellio, Fonseca, Vidoni), our Ch2 says 2021. Possibly a preprint vs journal version. Resolve.
- Ch2 free positioning: Olivo criticises Grassetti's weighting as arbitrary — biased toward what the author believes matters (made/missed shots) rather than objective efficiency per 100 possessions. **This is a ready-made argument for our outcome-independent buckets** (the "assisted axis dropped" reasoning).
- Novelty confirmed: Olivo does ridge/lasso/elastic-net, BPM fine-tuning, multi-league RAPM. **No play-type conditioning, no lineup-pair synergy.** O3 and O4 unclaimed.
- Still flagged from Wk2: lasso-multinomial authorship, Win Score/Berri.

## Next actions (Week 5)
1. **Deploy the Space to Hugging Face** (Tab 1 alone is enough for the MVT checkpoint). Bundle `rapm_baseline.parquet` + `rapm_dash.parquet`; set `RAPM_WAREHOUSE` to the Space's data path.
2. Resolve deployment friction (deps, caching, model-file size). Public URL live by end of week.
3. Wire `refresh.yml`: uncomment the HF push step, add `HF_TOKEN` secret, first real weekly run. `DASH_ALPHA` already pinned to 3162.3.
4. Write Ch3 (Data/ETL) + Ch8 (Dashboard) sections in parallel (writing chat).
5. Background, run solo: `ingest_shots.py --seasons 2007-2025` (Week 6 / O3) — the API 429s under concurrent pulls.

## Carry-forward notes (don't lose between chats)
- **Weekly cron α:** `DASH_ALPHA=3162.3`.
- **Week 9 hold-out filter:** the design `groups` int64 key splits as `season = groups // 100000`; filter `season == 2025` to pull 2025-26 back in as the test set. Same convention across all fits.
- **Design npz layout:** `_design.npz` holds `y`, `w`, `groups`, `x_path`; the sparse X lives in the sibling `_design.X.npz` (loaded separately by `fit_ridge_rapm.py`). Nothing missing.

## Scripts added/changed in Week 4
- `app/streamlit_app.py` (new — dashboard shell; Tab 1 live; env-configurable warehouse; Career-span label; `width="stretch"`)
- `.github/workflows/refresh.yml` (new — weekly dashboard refresh; HF push stubbed for Wk5; `DASH_ALPHA` pinned)
- `fit_ridge_rapm.py` — no code change; `--bootstrap 500` exercised for the first time (Week 3 ran it at 0)

## Scripts added/changed in Week 3
- `scripts/ingest_boxscore.py` (rewritten — per-game shards, 429 backoff, completeness gate)
- `scripts/build_player_id_map.py` (v2 — (name,season) key, merge-aware, hard invariant)
- `scripts/triage_id_collisions.py` (new — season/team collision triage)
- `config/id_merges.csv` (new — curated record of decision, 9 merges)
- `scripts/build_rapm_design.py` (real schema, distinct-five guard, (Season,Gamecode) key, --seasons/--prefix, luck-adjust hook)
- `scripts/fit_ridge_rapm.py` (names+season spans, --prefix/--min-games/--out, top-15/bottom-5 print)
- `scripts/build_league_averages.py` (new — per-season league 3P%)
- `scripts/build_stint_matrix.py` (patched — emits 3pa / non3_pts / xpts per team)

## Links
- GitHub repo: https://github.com/Spyro1322/euroleague-rapm
- HF Space URL: (pending Wk5)
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Current artifacts: warehouse/{stints, stints_ids, tagged_shots_ids, player_id_map, league_averages, rapm_design, rapm_players, rapm_baseline (now w/ RAPM_lo/RAPM_hi), rapm_dash, rapm_eval, rapm_olivo_baseline}
- Decision records: config/id_merges.csv, reports/id_collision_triage.csv