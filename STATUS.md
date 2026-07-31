# Thesis Status — Euroleague Shot-Context RAPM

_Last updated: end of Week 6_ · **_Submission: end of August 2026_**

## NEXT: draft Chapter 4
Ch4 (baseline ridge RAPM, O2) is **not started** and Ch5 cross-references it repeatedly — fit windows, possession floors, regularisation strengths, the Olivo replication. It is also the chapter with the least new thinking required: most of it is already recorded in this file and in the Week 3–4 reports. Do it first, then Ch7.

**The original Week 7 (role-conditional priors via usage/event-mix clustering) is DROPPED.** Rationale: only two of four contexts are identifiable, and their deviations are already statistically independent (−0.026), so refining the shrinkage anchors has little left to recover. It was a refinement to a model whose limiting factor turned out to be elsewhere. Record as a scope decision in Ch5 or Ch9; do not leave it looking outstanding.

**Order of remaining work:** Ch4, then Ch7 (evaluation results are in hand). Then the similarity finder + Tab 3 + short Ch6, and Ch9 limitations. Then Ch1/Ch3 corrections, the Ch2 citation check, cross-references and appendices, and a full read-through before it goes to the supervisor.

**Writing is the binding constraint. No new modelling** — evaluation is complete.

---

## Chapter status
| Ch | Topic | State |
|---|---|---|
| 1 | Introduction | drafted — O3 wording still says "play-type"; O4 flag now resolvable |
| 2 | Background | drafted — **needs the three-point repeatability citation Ch5 §5.8 leans on** |
| 3 | Data & ETL (O1) | drafted — needs corrections listed below |
| 4 | Baseline RAPM (O2) | **NOT STARTED — do first** |
| 5 | Shot-context RAPM (O3) | **drafted, 10 pp**, 2 flags |
| 6 | Similarity finder (O4) | not started, short |
| 7 | Evaluation | **NOT STARTED — results in hand** |
| 8 | Dashboard (O5) | drafted, updated 31 Jul |
| 9 | Limitations | not started |

---

## O3 RESULT (Chapter 5) — established
Four location contexts, per-bucket ridge fits shrunk toward each player's overall RAPM.

1. **Taxonomy correction.** Situation flags (FASTBREAK / SECOND_CHANCE) are populated on **made shots only** — transition 1,954 rows with zero misses, second_chance 2,741 with one. They cannot support an efficiency rating, and precedence over location also stripped made fastbreak/putback attempts out of the location contexts. Ignoring them moves every context onto its published league value: at_rim 0.546 → **0.638**, above_break 0.317 → **0.353**, corner 0.393 → **0.414**, mid_range 0.369 → **0.386**.
2. **Shot-value hierarchy reproduced untuned:** at_rim 127.6 ≈ corner 124.2 > above_break 105.8 > mid_range 77.1 pts/100.
3. **Signal grew with the ETL.** at_rim unshrunk correlation with overall RAPM: **+0.052 / −0.260** on one season → **+0.408 / −0.481** across nineteen.
4. **Two-point contexts identified, three-point not**, stable across three windows sharing as few as 5 of 19 seasons: at_rim 0.481 / 0.478 / 0.472; mid_range 0.372 / 0.337 / 0.362; above_break 0.066 / 0.098 / 0.046; corner 0.016 / 0.044 / 0.045.
5. **Not a sample-size limitation.** above_break has *more* on-court support than at_rim in the dash window (median 286 vs 271) and still shows nothing.
6. **Contexts are not redundant.** corr(value) = 0.707 but corr(deviation) = **−0.026**; the 0.707 is entirely the shared prior (predicted null 0.709).

Face validity: Tavares tops at-rim defence (4.96 on a 3.30 prior); rim-tilt (at_rim − mid_range, in which the prior cancels exactly) separates Fall and Tavares from Howard, Sloukas, Baldwin. Positional recovery is real but weak: corr(rim_tilt, own rim shot share) = **0.175** at n = 296.

---

## EVALUATION RESULT (Chapter 7) — NEW, and it is a null for the core hypothesis
**Box-score metrics outperformed RAPM at predicting held-out 2025-26 game margin.** Train 2020–2024, hold-out 2025-26, frozen scaling coefficients, 402 games.

| arm | RMSE | vs naive | corr | winner | R² | slope |
|---|---|---|---|---|---|---|
| win_score | 11.604 | **+5.08%** | 0.322 | 65.4% | 0.099 | 3.19 |
| pir | 11.910 | +2.58% | 0.268 | 63.4% | 0.051 | 2.70 |
| rapm | 12.009 | +1.77% | 0.226 | 63.2% | 0.035 | **1.57** |
| shotctx | 12.064 | +1.32% | 0.216 | 64.4% | 0.026 | 1.43 |
| naive | 12.225 | — | — | 63.4% | 0 | — |

Common support (≥85% of slots rated, 73 games) is worse for RAPM still: **−1.69%**, negative R². **But do not lean on that subset** — 73 games is within sampling noise, and the criterion is gated by the box-score arms' coverage (453 rated players vs RAPM's 677), so it selects games played by established high-minute players, compressing exactly the range where RAPM discriminates. **The 402-game result is the reliable one.**

**Stint-level is a null and should be reported as one.** All four arms improve on naive by <0.11%, R² ≈ 0.002. Cause: 14,067 stints over 402 games ≈ 35 stints/game ≈ 4 possessions per stint. At four possessions the target (margin per 100) moves ±50–75 on a single make; noise sd ≈ 126 against a signal spanning ~15. Ceiling R² ≈ 0.01 regardless of rating quality. **This is a legitimate methodological finding: the stint is the wrong unit at which to compare season-level ratings**, and stating it pre-empts the question of why the obvious test was not used.

**Slope finding, real regardless of which arm wins.** RAPM is in points/100 already, so a calibrated rating predicts with slope 1.0. The fitted slope is **1.57** (1.99 at stint level) — the penalty shrinks ratings to ~⅔ of the spread that best predicts out of sample. CV minimises in-window error, not out-of-sample calibration, and the CV curve here is flat over an order of magnitude. `sweep_alpha_holdout.py` tests how much of the gap this explains. Box-score arms fail the opposite way (slopes 2.7–3.2 on unitless z-scores).

**Interpretation to develop in Ch7:** game margin is largely team quality. PIR and Win Score reward usage, and usage concentrates on strong teams' best players, so a lineup's summed box-score rating partly encodes team strength — which RAPM removes *by construction*. This target therefore partly rewards not adjusting. Testable by correlating each metric against team win percentage.

**Write it honestly and lead with the result.** Ch5's finding stands entirely independently of this chapter. A thesis that establishes one thing and reports a clean null on another is stronger than one that hunts for a favourable test.

---

## Corrections to earlier claims
- **The location thresholds are CONFIRMED, not struck** (an earlier STATUS said to strike them). `play_context.py`: rim radius **200 cm**, corner sideline minimum **660 cm**, corner depth maximum **220 cm** (my reconstruction fitted 225). Basket at origin, centimetres, x = sideline, y = depth. Arc ≈ 675. Axis orientation, previously marked provisional in the source, is confirmed by fitted geometry: corners median |x| 683 / depth 37, above-break 426 / 614.
- **The 2008 relabel discrepancy (0.922) is EXPLAINED.** `RIM_ACTIONS = {LAYUPMD, LAYUPATT, DUNK}` classify as at_rim **regardless of coordinates** — action code overrides geometry. Those codes do not appear in 2023 at all, so a reconstruction fitted there could not learn the branch, while early seasons use them heavily. **The feed's action vocabulary is not constant across the study period** — a Ch3 finding as much as a Ch5 one.
- **`corr(attempts, deviation) = −0.994` is STRUCK** and must not appear anywhere. Invalid: raw deviation sd is not comparable across contexts with different outcome variance (3-pt y sd ~117–141 vs 2-pt ~75–83), so it measured shot variance and reported the verdict backwards. Normalised, the same data gives **+0.925**. Use `assess_identifiability.py`.
- **PIR verified exactly** — recomputed from components, **0 disagreements across 117,089 rows** against the feed's Valuation column. Worth stating in Ch7: the baseline being argued against is the competition's own metric, not an approximation of it.
- **Boxscore `Player_ID` carries trailing whitespace** (`'P000007   '`). `build_player_id_map.py` strips it; `build_eval_metrics.py` originally did not, giving **zero** join overlap. Fixed. Any new script touching boxscore IDs must strip.
- **PIR and Win Score correlate at 0.807**, not >0.95 — genuinely distinct measurements, so report them as two baselines rather than one approach twice.
- **Scoring inflation across the study period:** PIR/40 rises 15.95 → 17.80, Win Score 6.24 → 7.38. Within-season standardisation is therefore a necessary methodological choice with evidence, not a default.
- **The refresh is a reproduction path, not a live cron.** 2025-26 completed on 24 May and the next season starts after submission, so there is no new data in the thesis window. O5's weekly refresh is a fact about the calendar, not a scope change — the mechanism exists and would run weekly in season. Documented in Ch8 §8.7. `refresh.yml` deleted: `warehouse/` and `data/` are gitignored (~260 MB) so CI could never rebuild, and with no ingest step it would have exited green having changed nothing.
- **`stints_ids.parquet` does NOT correspond to the RAPM designs.** 296,683 design rows vs 279,174 stints all-time, and no filter reproduces any design's row count. `build_rapm_design.py` re-derives stints in memory from the PBP. **Live trap.**
- **Coordinate coverage is 1.000 every season**, not 0.97–0.99. The earlier figure used `COORD_X != 0`, counting a dead-centre shot as missing.
- **Unmapped shooters: 0 of 610,554.** The item carried since Week 4 was a one-season artefact.

---

## Open items
- **`rapm_eval_full`** — unfiltered refit (677 players, floors disabled) used for evaluation, because the display floor was capping the RAPM arm's coverage. Keep the floored version for the dashboard; note the distinction in Ch7.
- **Orientation failures concentrated in 2013–14** — 0.492% overall (3,020 of 613,574) but **3.3% in 2014**, ~27× elsewhere. Week 1's 0.12% came from a five-game-per-season sample that would have missed it. **Ch9.**
- **`validate_tagging.py` has not been run against the four-context taxonomy.** The Week 2 manual validation predates both the removal of the situation flags and the action-code era finding. A clean pass on two pre-2015 seasons would close it and is a strong Ch3 sentence. **The one piece of validation work still worth doing.**
- **Quantify the action-code share by season** — the number behind Ch5 §5.2.5 and the 2008 discrepancy.
- **2018 boxscore gate failing** — `_MISSING.csv` gamecode 21, no `_SUCCESS`.
- **`data/landing/` unused duplicate** of root `landing/` (~99 MB). Safe to delete.
- **PAT still needs revoking** — `repo_token.txt` reached `git push` before protection blocked it. File removed and `.gitignore` updated; the token itself must be revoked and reissued.
- **Supervisor email on the O4 scope change** — drafted, send if not already sent.
- Verdict is recomputed each export; `above_break_three` sits at 0.098 against a 0.10 threshold and could flip. Consider pinning as alpha is pinned. Low priority now the season is complete.

---

## Carry-forward
- **Always `--force-signs +1,-1`** on `fit_shotctx_rapm.py`.
- **Design stems are not uniform:** all-time is `rapm_design` + `rapm_players`; `rapm_baseline.parquet` is only the leaderboard. `dash`/`eval` use `rapm_{w}_design` + `rapm_{w}_players`.
- **Week 4 fit command** (shell history, reproduces the deployed artifact): `fit_ridge_rapm.py --prefix rapm_dash --bootstrap 500 --out rapm_dash` — default floors, **no** `--alpha` (CV chose 3162.3). `--out` takes a stem, not a path. Baseline used `--prefix rapm --alpha 1995.3 --out rapm_baseline_ci`. **Dump the relevant history lines into `docs/` before the buffer rolls — Ch4 needs the exact commands and they exist nowhere else.**
- **Three season-range conventions in one pipeline:** `ingest_pbp`/`ingest_shots` use `--seasons 2007-2025`; `ingest_boxscore` uses `--start/--end`; `build_rapm_design` uses `--seasons 2007:2025`. Ch9 reproducibility note.
- **Player map layout:** `col` is the within-block index 0..n−1; `off_offset` a constant base (0), `def_offset` a constant base (n).
- **`player_id` is a String**, never an int. Boxscore `Player_ID` needs stripping.
- **Composite game key:** `Season * 100000 + Gamecode`; season = `groups // 100000`.
- **Data layout:** boxscores `landing/boxscore_players/`, PBP `data/pbp_lineups/`, shots `data/shots/`, warehouse at repo root.
- **Alphas:** `DASH_ALPHA=3162.3` (overall), `SHOTCTX_ALPHA=3162` (per-bucket). CV curves flat near the minimum for both.
- **Tagged shots:** 610,554 rows, 19 seasons, 99.89% PBP join. Distinctness violations 845 (0.138%).

---

## Scripts
**Week 6 (O3):** `tag_shots.py` (pre-2015 crash fixed; flags ignored; per-shard dtype-drift reader; orientation failures excluded not inverted), `build_shotctx_design.py`, `fit_shotctx_rapm.py`, `assess_identifiability.py`, `export_shotctx_parquet.py`, `relabel_four_bucket.py`, `derive_location_rules.py` (superseded, keep for audit trail), `build_player_id_map.py` (full-range glob, silent-skip removed).

**Evaluation (new):** `build_eval_metrics.py` (PIR + Win Score, verified), `evaluate_holdout.py` (stint level), `evaluate_game.py` (game level, primary), `sweep_alpha_holdout.py` (regularisation vs out-of-sample prediction).

**Deployment:** `refresh_dashboard.sh` (reproduction path), `smoke_test_dashboard.sh` (clean-venv mirror test).

**Diagnostics kept for the audit trail:** `diagnose_wk6_round2.py`, `inspect_landing.py`, `probe_shot_bridge.py`, `audit_data_trees.py`.

## Links
- Main repo: https://github.com/Spyro1322/euroleague-rapm
- Mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard
- Live dashboard: https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Reports: `reports/{wk6_retag,wk6_idmap,wk6_o3_full,wk6_identifiability,eval_metrics,eval_holdout,eval_game,sweep_alpha}`