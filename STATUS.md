# Thesis Status — Euroleague Shot-Context RAPM

_Last updated: end of Week 6 (31 July 2026)_ · **_Submission: end of August 2026 — ONE MONTH REMAINING_**

## Read this first
**Writing is now the bottleneck, not modelling.** Ch1, 2, 3, 8 are drafted. Ch4, 5, 6, 7, 9 are not. **Evaluation (held-out 2025-26 vs PIR / WINSCORE / classical RAPM) has not been started** and is the deliverable an examiner will look for hardest. Allowing a week for supervisor feedback and submission mechanics leaves **three working weeks**.

**Plan:**
- **Wk A (1–7 Aug)** — Ch5 and Ch4 drafted. Week 6 closed. STATUS + Ch1/Ch3 corrections.
- **Wk B (8–14 Aug)** — **Evaluation.** PIR/WINSCORE baselines, hold-out protocol, RMSE / ranking stability / calibration, comparison table. Draft Ch7 alongside. Highest risk; protect its slack.
- **Wk C (15–21 Aug)** — Similarity finder + Tab 3 + short Ch6. Ch9 limitations. Ch1/Ch3 fixes.
- **Wk D (22–31 Aug)** — Supervisor feedback, polish, defence slides, submit.

## O4 — RESOLVED: similarity finder, NOT lineup-pair synergy
Decided 31 July after four weeks open. The similarity finder is cosine distance in the four-dimensional bucket space and runs directly off the per-bucket fits already on disk — roughly a day. PyMC synergy is 16–20 h with the highest sampling/convergence variance in the plan and no fallback, and Week 6 already overran. Ch5's result is strong enough that the thesis does not need Ch6 to carry a contribution.

**Action: tell the supervisor in writing, now.** Frame it as: the shot-context work produced a stronger and more surprising result than expected, and the evaluation objective needs the remaining time more than a second modelling layer does. Dashboard drops from five tabs to four (Leaderboard, Shot context, Similarity, Methodology). Ch6 becomes short.

---

## O3 RESULT — the Week 6 contribution
Four location buckets (`at_rim`, `mid_range`, `corner_three`, `above_break_three`), per-bucket ridge fits hierarchically shrunk toward each player's overall RAPM. Six pieces of evidence, all reproducible from `reports/`:

**1. Taxonomy correction.** The Euroleague feed populates FASTBREAK / SECOND_CHANCE on **made shots only** (2023: transition 1,954 rows with zero misses; second_chance 2,741 with one). Those buckets cannot support an efficiency rating, and because the tagger gives them precedence over location they also stripped made fastbreak/putback attempts out of the location buckets. Ignoring the flags fixes both, and every bucket lands on its published league value:

| bucket | flags active | flags ignored | league norm |
|---|---|---|---|
| `at_rim` | 0.546 | **0.638** | ~0.62–0.66 |
| `above_break_three` | 0.317 | **0.353** | ~0.35–0.36 |
| `corner_three` | 0.393 | **0.414** | above-break + 5–8 pp |
| `mid_range` | 0.369 | **0.386** | ~0.40 |

**2. Shot-value hierarchy reproduced with no tuning:** `at_rim` 127.6 ≈ `corner_three` 124.2 > `above_break_three` 105.8 > `mid_range` 77.1 pts/100. (Corner threes sit level with the rim in 2023 but slightly below across all time — a real trend, worth a sentence.)

**3. Signal grew with the ETL.** `at_rim` unshrunk correlation with overall RAPM went from **+0.052 / −0.260** on one season to **+0.408 / −0.481** across nineteen. This is the quantified justification for the full-range re-tag.

**4. Two-point buckets identified, three-point buckets not** — stable across three windows sharing as few as 5 of 19 seasons:

| bucket | baseline | dash | eval | verdict |
|---|---|---|---|---|
| `at_rim` | 0.481 | 0.478 | 0.472 | STRONG |
| `mid_range` | 0.372 | 0.337 | 0.362 | STRONG |
| `above_break_three` | 0.066 | 0.098 | 0.046 | NONE |
| `corner_three` | 0.016 | 0.044 | 0.045 | NONE |

**5. Not a sample-size artefact.** `above_break_three` has *more* on-court support than `at_rim` in the dash window (median 286 vs 271) and still shows no signal. This pre-empts the obvious objection and is probably the strongest single sentence in Ch5.

**6. The buckets are not redundant.** `corr(at_rim_value, mid_range_value) = 0.707`, but `corr(at_rim_deviation, mid_range_deviation) = −0.026`. Both buckets shrink toward the same prior, so the 0.707 is *entirely* the shared prior (predicted null 0.709). Once removed, the bucket-specific components are statistically independent — each carries information the other does not, and neither restates overall DRAPM.

**Face validity:** Tavares tops at-rim defence (4.96, highest prior 3.30), then Hayes, Poirier, Costello. Rim-tilt (`at_rim − mid_range`, in which the shared prior cancels exactly) separates Fall and Tavares at one end from Howard, Sloukas and Baldwin at the other — position recovered from possession-level scoring alone, with no height or role input.

**Honest limit:** `corr(rim_tilt, own rim shot share) = 0.175` at n = 296 (~3 SE from zero). Positional structure is real but weak, consistent with the known difficulty of attributing defensive credit within a five-man unit. **Ch9.**

---

## CORRECTIONS TO EARLIER CLAIMS — read before writing anything
- **STRIKE `corr(attempts, deviation) = −0.994`.** That statistic was invalid: it compared raw deviation sd across buckets with very different outcome variance (3-pt y sd ~117–141 vs 2-pt ~75–83), so it measured shot variance, not identifiability, and reported the verdict backwards. Normalised by `y_sd / √(att per player)` the same baseline data gives **+0.925**. Identifiability is now assessed by `scripts/assess_identifiability.py`.
- **STRIKE the "pinned" thresholds `r < 200` / `|x| ≥ 660`.** They were reverse-engineered from 2023 labels and are *not* exact — the regression check against `play_context.classify` scores 0.99929 overall but **0.922 on 2008**. Ch5 must document what `scripts/play_context.py` actually contains.
- **Week 5's "shot ingest COMPLETE → Week 6 blocker cleared" was wrong.** The raw ingest completed; the *tagger* had only ever run on 2023, because `bool(int(FASTBREAK))` raises on the nulls present in every pre-2015 season. Fixed; 610,554 rows now tagged across 19 seasons.
- **The Week 5 "O3 Option 1 / per-column season mask / 2016 boundary" decision is SUPERSEDED**, not dropped. It was correct on the evidence then available and is invalidated by the makes-only finding. Record the chain in Ch5 — it is a methods strength.
- **`stints.parquet` / `stints_ids.parquet` do NOT correspond to the RAPM designs.** Design rows exceed stint rows for identical ranges (296,683 vs 279,174 all-time), and no filter combination reproduces any design's row count or multiset of game keys. `build_rapm_design.py` re-derives stints in memory from the PBP. **Live trap — never assume design row *i* ↔ stints row *i*.**
- **`refresh.yml` could never have worked.** `warehouse/` and `data/` are gitignored (~260 MB), so a CI runner has nothing to build from; and with no ingest step it would have refit identical data and exited green having changed nothing. Replaced by `scripts/refresh_dashboard.sh`. Documented in Ch8 §8.7.
- **Coordinate coverage is 1.000 in every season**, not the 0.97–0.99 recorded in Week 5. That figure used `COORD_X != 0`, which counts a dead-centre shot as missing.
- **Unmapped shooters: 0 of 610,554.** The open item carried since Week 4 was a one-season artefact.

---

## Key decisions (Week 6)
- **Four location buckets, situation flags ignored, identical across all three windows.**
- **Per-bucket independent ridge fits, not one stacked matrix.** Buckets partition shots, so the stacked design is block-diagonal and the two are mathematically identical. Easier to diagnose; per-bucket alpha. ("Stacked design matrix" in the timeline is a naming change, not a methods change.)
- **Units:** `w` = bucket attempts, `y` = 100 × points / attempts = points per 100 possessions-of-that-type. Same denominator semantics as overall RAPM, different subpopulation — which is what makes shrinking toward it legitimate.
- **Scope caveat (Ch5):** buckets cover possessions ending in a field-goal attempt. Turnovers and free-throw-only possessions sit outside the context model and remain in the overall model.
- **`y` weighted-centred + unpenalised intercept.** Without this each bucket's league mean (~128 pts/100 at rim) is absorbed into the ten player coefficients per row, so coefficients read as absolute efficiency rather than deviations — caught in fixture testing at +10 to +13 instead of ≈0.
- **Sign convention `mu_off = +ORAPM`, `mu_def = −DRAPM`**, established from the two highest-signal buckets. **Always `--force-signs +1,-1`**; per-bucket calibration is noise-driven on thin buckets and got `corner_three` backwards.
- **Design source is `tagged_shots_ids` alone** — it already carries `off_players`/`def_players`, so no stints file, no `pbp_poss`, no shot→stint bridge.
- **Unidentified buckets are drawn ON the prior ring**, greyed and daggered, not hidden. For a bucket with no signal the model's best estimate genuinely *is* the overall rating, so the flatness of those axes becomes the visible finding. Low-support-but-identified buckets gap instead — a different claim, different treatment.
- **Sub-floor prior:** 705 of 2,183 baseline players have no leaderboard row and shrink toward 0 rather than their overall rating. Defensible (0 is the league mean) but **state it as a modelling choice in Ch5**.

---

## Open items
- **2008 relabel discrepancy (0.922)** — pinned rules vs `play_context.classify`, concentrated in at-rim/mid-range. Either 2008 coordinates are scaled differently or `classify` has an action-code branch. **Only matters for Ch5's rule description, not for results**, since the pipeline uses `classify` throughout.
- **Orientation failures concentrated in 2013–14.** 0.492% overall (3,020 of 613,574) but **3.3% in 2014** alone, ~27× the rate elsewhere. Week 1's 0.12% came from a 5-game-per-season sample that would have missed it. Reconstruction quality is not uniform across seasons — **Ch9**.
- **2018 boxscore gate still failing** — `_MISSING.csv` gamecode 21, no `_SUCCESS`. `ingest_boxscore.py --retry-only --seasons 2018`.
- **`data/landing/` is an unused duplicate** of root `landing/` (~99 MB). `build_player_id_map.py` reads root. Safe to delete.
- **Verdict is recomputed each refresh.** `above_break_three` sits at 0.098 against a 0.10 threshold — one week of data could flip it and change what the dashboard renders. Consider pinning the verdicts as alpha is pinned.
- **PAT hygiene:** `repo_token.txt` was committed and blocked by GitHub push protection. File removed and `.gitignore` updated, but **the token itself must be revoked and reissued** — it reached `git push`.
- Rolling-window sensitivity (3 vs 5 season) — deferred, low priority against the schedule.

---

## Carry-forward (don't lose between chats)
- **Always `--force-signs +1,-1`** on `fit_shotctx_rapm.py`.
- **Design stems are NOT uniform:** all-time is `rapm_design` + `rapm_players`; `rapm_baseline.parquet` is only the leaderboard. `dash`/`eval` follow `rapm_{w}_design` + `rapm_{w}_players`.
- **Player map layout:** `col` is the within-block index 0..n−1; `off_offset` a constant base (0), `def_offset` a constant base (n). Offensive column = `off_offset + col`.
- **`player_id` is a String** (`P005791`, `PJKO`, `000595`, `A1`), never an int.
- **Composite game key:** `Season * 100000 + Gamecode`; season = `groups // 100000`.
- **Coordinates are centimetres**; FIBA arc r ≈ 675, corners 660.
- **Data layout:** boxscores `landing/boxscore_players/`, PBP `data/pbp_lineups/`, shots `data/shots/`, warehouse at repo root. `data/warehouse/` is empty.
- **Alphas:** `DASH_ALPHA=3162.3` (overall), `SHOTCTX_ALPHA=3162` (per-bucket). Do not conflate; CV curves are flat near the minimum for both, so a re-run can wander an order of magnitude.
- **Distinctness violations:** 845/610,554 = 0.138% baseline, consistent with Week 1's 0.12%.
- **Week 9 hold-out filter:** `season == 2025`.

---

## Scripts added/changed in Week 6
- `tag_shots.py` — **fixed the pre-2015 crash** (`bool(int(FASTBREAK))` on nulls); situation flags ignored by default; per-shard tolerant reader for Null-vs-String dtype drift; **orientation failures detected rather than silently inverted** (the old `split_off` assumed Lineup_B whenever the shooter wasn't in Lineup_A, including when he was in neither); per-season join/coverage diagnostics with a hard floor.
- `build_shotctx_design.py` — per-bucket designs from tagged shots; re-derives lineup distinctness; asserts the id map can't collapse two players onto one column; purges stale bucket artifacts; refuses precedence-tagged input.
- `fit_shotctx_rapm.py` — per-bucket weighted ridge shrunk toward overall RAPM via `c = β − μ`; unpenalised intercept; weighted centring; `--force-signs`; GroupKFold by game.
- `assess_identifiability.py` — **NEW.** The corrected diagnostic. Normalises deviation by outcome variance; uses unshrunk correlation as the primary measure; per-bucket verdicts.
- `export_shotctx_parquet.py` — sign normalisation with hard assertions against the leaderboard; support gating; carries `signal`/`verdict` into the parquet.
- `relabel_four_bucket.py` — pinned-rule relabeller with per-season regression check (now only a cross-implementation test, since the tagger emits four buckets directly).
- `derive_location_rules.py` — one-off threshold recovery. Superseded; keep for the audit trail.
- `refresh_dashboard.sh` — **NEW.** Operator-triggered refresh replacing the unrunnable cron.
- `smoke_test_dashboard.sh` — **NEW.** Clean-venv mirror test: import resolution, synthetic parquet, headless run, health check, log scan.
- `build_player_id_map.py` — full-range glob; silent-skip `except` replaced with a hard exit.
- Diagnostics kept for the audit trail: `diagnose_wk6_round2.py`, `inspect_landing.py`, `probe_shot_bridge.py`, `audit_data_trees.py`.

## Thesis drafts
- **Ch3** — needs the two-tree layout correction, the §3.4 taxonomy flag resolved to the Week 6 decision, the 0.138% distinctness rate, coordinate coverage 1.000, and 0 unmapped shooters.
- **Ch8** — updated 31 July: four tabs, §8.7 rewritten for the operator-triggered refresh, charting-dependency record, friction table extended. One flag remains: proposal/Ch1 still name Hugging Face Spaces for O5.
- **Ch1** — O3 wording still says "play-type"; relabel to "shot-context". O4 flag now resolvable to the similarity finder.
- **Ch5** — not started. All six evidence points in hand. **Start here.**

## Links
- Main repo: https://github.com/Spyro1322/euroleague-rapm
- Mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard
- Live dashboard: https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Week 6 reports: `reports/{wk6_retag,wk6_idmap,wk6_o3_full,wk6_identifiability,wk6_rules,shotctx_*_fit_report,shotctx_*_identifiability,shotctx_*_export}`