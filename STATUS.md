# Thesis Status — Euroleague Shot-Context RAPM

_Last updated: end of Unit 8b (verdict pinning + fit provenance)_ · **_Submission: end of August 2026_**

## NEXT: Unit 7 — draft Chapter 4, then Chapter 7
Both are writing-only; every number exists in `reports/`. **Ch4 is blocking** — Ch5 and Ch6 both cross-reference it (fit windows, possession floors, regularisation strengths, the Olivo replication).

**Fit provenance is DONE** — `docs/fit_commands.md` holds every invocation Ch4/Ch5/Ch7 cite, tiered VERIFIED / VERIFIED BY ENTAILMENT. Shell history was recovered before the buffer rolled. Ch4 can be drafted straight off it; do not re-derive commands in-session.

**Order of remaining work:** Ch4 → Ch7 (Unit 7). Then Unit 9: Ch1/Ch3 corrections, Ch2 citation check, cross-references, appendices, full read-through, **send to supervisor at the close of Unit 9**. Unit 10 is buffer — no new features.

**Writing is the binding constraint. No new modelling.** Modelling and evaluation are both complete.

---

## UNIT 8b — identifiability verdicts pinned, fit provenance recovered
Short unit between Unit 8 and Unit 7's writing. Two closed items, one new Ch5 result.

**The verdict rule was duplicated across two scripts, and the copy that governed the dashboard was not the documented one.** `assess_identifiability.py` printed a verdict and wrote it to `reports/`; `export_shotctx_parquet.py` **recomputed the same thresholds inline** and wrote them into the parquet. The mirror ships parquet only and never sees `reports/`, so the export's inline copy was the sole determinant of what Tab 2 rendered. Editing the assess script alone would have changed nothing visible. Fixed: `scripts/identifiability_pins.py` is now the single source of truth, imported by both.

**`above_break_three` is pinned NONE, on three independent lines of evidence:**
1. **magnitude** — |corr| = 0.066 / 0.098 / 0.046 (baseline/dash/eval), all below the 0.10 threshold
2. **sign** — the 0.098 is `corr_def` **positive**, the wrong direction for a real defensive effect. at_rim (−0.481/−0.478/−0.472) and mid_range (−0.372/−0.306/−0.362) are negative in every window. `signal = max(|·|)` discards this; `sign_check()` now surfaces it
3. **regularisation** — CV selected the **grid ceiling** (α = 10000) for `eval/above_break_three`. Maximum available shrinkage toward the prior is the same claim as "no recoverable individual effect", reached independently of the correlation test

The 0.098 is in the **dash** window — the dashboard default — which is why an unpinned recompute mattered. Pinned, a drifting re-fit prints a warning and publishes the pin instead of silently rendering a suppressed spoke.

**Also explains two diagnostics that looked anomalous:** `eval/above_break_three` `dev_sd` 0.309 vs 0.734/0.761 elsewhere, and eval being the only window with ambiguous normalised separation (+0.353 vs +0.925/+0.982). Both follow from 10× more shrinkage on that one bucket. **Verdicts use unshrunk coefficients and are α-independent**, so nothing in the O3 result moves.

**Tab 2 gained the WEAK tier its own docstring already specified.** The code checked only `verdict != "NONE"`, collapsing STRONG and WEAK — so a bucket crossing into WEAK would have rendered identically to at_rim with no caveat. Now three treatments: STRONG solid, WEAK gold diamond + ‡ + caveat, NONE hollow grey pinned to the ring + †. No bucket is currently WEAK; a ‡ appearing on the live app is a bug.

**Deploy verified 1 Aug 2026 (second pass):** clean-venv smoke test passed, Streamlit Cloud build succeeded, Tab 2 clicked through in both windows with the compare toggle. Three-point spokes on the ring, hollow grey, † present, deviation bars grey at zero, no ‡.

---

## Chapter status
| Ch | Topic | State |
|---|---|---|
| 1 | Introduction | drafted — O3 wording still says "play-type"; O4 flag now resolvable |
| 2 | Background | drafted — **needs the three-point repeatability citation Ch5 §5.8 leans on** |
| 3 | Data & ETL (O1) | drafted — needs corrections listed below |
| 4 | Baseline RAPM (O2) | **NOT STARTED — do first** |
| 5 | Shot-context RAPM (O3) | drafted, 10 pp, 2 flags — **§5.8 gains the sign + grid-ceiling evidence (Unit 8b)** |
| 6 | Shot-context archetypes (O4) | **drafted, ~5 pp, 2 flag boxes** |
| 7 | Evaluation | **NOT STARTED — results in hand** |
| 8 | Dashboard (O5) | drafted — **needs Tab 3 section**; deploy verified 1 Aug (see below) |
| 9 | Limitations & future work | **drafted, ~5 pp, 1 flag box** |

---

## O4 RESULT (Chapter 6) — NEW, delivered as archetypes not similarity
O4 was rescoped twice: synergy → similarity finder → archetypes. **The second rescope was forced by a failed validation, not by convenience**, and that sequence is the chapter's argument.

**Space.** Per-context deviation vectors, four dimensions (at_rim, mid_range × off, def). Deviations not values (corr(value)=0.707 is entirely the shared prior, predicted null 0.709). Each axis z-scored — above_break has the *largest* raw sd (0.75–0.77) and the *weakest* identifiability, so unnormalised distance would be dominated by noise. Three-point contexts excluded: including them cuts the reliably-placed population from **379 to 119**.

**Space is clean.**
- Four near-equal PCs, leading component **0.310**. PC1 contrasts at_rim_off against mid_range_off — Ch5's rim-tilt axis recovered unsupervised.
- corr(distance, |Δprior|) = **+0.057** over 71,631 pairs. Not a leaderboard in disguise.

**Ranked similarity FAILS cross-window replication.** dash (2021–25) vs eval (2020–24), 310 shared players:

| K | Jaccard | chance | ratio |
|---|---|---|---|
| 1 | 0.094 | 0.003 | 29.0× |
| 3 | 0.083 | 0.010 | 8.5× |
| 5 | 0.096 | 0.016 | 6.0× |
| 10 | 0.134 | 0.032 | 4.1× |

**Do not read the ratio-to-chance column as a pass.** Those windows share four of five seasons, so the expectation is near-complete agreement. 87% turnover on ~80% shared data is a failure. Agreement is **flat in K** — an earlier claim in-session that the head of the list was more stable was wrong (the ratio rises only because the chance baseline shrinks). Same-nearest-neighbour: 9.4%.

**Archetype membership DOES replicate.** ARI, k-means fitted independently per window: k=3 +0.335, k=4 +0.415, **k=5 +0.429**, k=6 +0.382, k=7 +0.315, k=8 +0.253. Stable 3–7, so **k is presentational, not tuned**.

**The contrast is the finding:** region membership survives what individual ranking does not, same players, same space, same fits — only the granularity of the claim differs.

**Caveat that bounds it:** cluster *sizes* are mobile. An earlier fit gave 54/70/83/63/92 against the current 44/99/73/87/76. Regions replicate; boundaries do not.

**Archetypes at k=5** (379 players; ids are arbitrary and change on re-run):
| id | n | rim off/def | mid off/def | representative |
|---|---|---|---|---|
| A0 | 44 | −0.33 / −0.96 | +0.67 / −1.45 | James, Punter, Vesely, Loyd |
| A1 | 99 | −0.06 / −0.68 | −0.17 / +0.86 | Sloukas, Calathes, Baldwin, Smits |
| A2 | 73 | −0.92 / +0.75 | +0.81 / −0.09 | Larkin, Clyburn, Weiler-Babb |
| A3 | 87 | +1.09 / −0.08 | +0.13 / −0.16 | Tavares, Vezenkov, Kalinic, Hezonja |
| A4 | 76 | −0.09 / +0.80 | −1.09 / −0.02 | Walkup, Shengelia, Bonga, Moneke |

**Groups cut across positions** — Tavares in A3, Vesely in A0. Consistent with corr(rim_tilt, own rim share) = 0.175. A0 is negative on three of four axes; treat as a residual group, not a style.

---

## O3 RESULT (Chapter 5) — established, unchanged
Four location contexts, per-bucket ridge fits shrunk toward each player's overall RAPM.

1. **Taxonomy correction.** FASTBREAK / SECOND_CHANCE populated on **made shots only** (transition 1,954 rows zero misses; second_chance 2,741, one). Precedence over location also stripped made fastbreak/putback attempts out of the location contexts. Ignoring them moves every context onto its published league value: at_rim 0.546 → **0.638**, above_break 0.317 → **0.353**, corner 0.393 → **0.414**, mid_range 0.369 → **0.386**.
2. **Shot-value hierarchy reproduced untuned:** at_rim 127.6 ≈ corner 124.2 > above_break 105.8 > mid_range 77.1 pts/100.
3. **Signal grew with the ETL.** at_rim unshrunk correlation with overall RAPM: **+0.052 / −0.260** on one season → **+0.408 / −0.481** across nineteen.
4. **Two-point contexts identified, three-point not**, stable across three windows sharing as few as 5 of 19 seasons: at_rim 0.481 / 0.478 / 0.472; mid_range 0.372 / 0.337 / 0.362; above_break 0.066 / 0.098 / 0.046; corner 0.016 / 0.044 / 0.045.
5. **Not a sample-size limitation.** above_break has *more* on-court support than at_rim in the dash window (median 286 vs 271) and still shows nothing.
6. **Contexts are not redundant.** corr(value) = 0.707 but corr(deviation) = **−0.026**; predicted null 0.709.
7. **The three-point null is triply evidenced** (Unit 8b): magnitude below threshold, `corr_def` **wrong-signed** in all three windows, and CV selecting the **α grid ceiling** for `eval/above_break_three`. Verdicts are now pinned in `scripts/identifiability_pins.py` rather than recomputed at export.
8. **α is CV-selected per bucket, not pinned.** Twelve fits: 3162 everywhere except `baseline/corner_three` 1000, `eval/corner_three` 1000, `eval/above_break_three` 10000. Every exception is a three-point bucket.

Face validity: Tavares tops at-rim defence (4.96 on a 3.30 prior); rim-tilt separates Fall and Tavares from Howard, Sloukas, Baldwin. Positional recovery weak: corr(rim_tilt, own rim shot share) = **0.175** at n = 296.

---

## EVALUATION RESULT (Chapter 7) — a null for the core hypothesis
**Box-score metrics outperformed RAPM at predicting held-out 2025-26 game margin.** Train 2020–2024, hold-out 2025-26, frozen scaling coefficients, 402 games.

| arm | RMSE | vs naive | corr | winner | R² | slope |
|---|---|---|---|---|---|---|
| win_score | 11.604 | **+5.08%** | 0.322 | 65.4% | 0.099 | 3.19 |
| pir | 11.910 | +2.58% | 0.268 | 63.4% | 0.051 | 2.70 |
| rapm | 12.009 | +1.77% | 0.226 | 63.2% | 0.035 | **1.57** |
| shotctx | 12.064 | +1.32% | 0.216 | 64.4% | 0.026 | 1.43 |
| naive | 12.225 | — | — | 63.4% | 0 | — |

Common support (≥85% of slots rated, 73 games) is worse for RAPM still: **−1.69%**. **Do not lean on that subset** — 73 games is sampling noise and the criterion is gated by the box-score arms' coverage (453 rated vs RAPM's 677), selecting games played by established high-minute players and compressing the range where RAPM discriminates. **The 402-game result is the reliable one.**

**Stint-level is a null and should be reported as one.** All four arms improve on naive by <0.11%, R² ≈ 0.002. 14,067 stints / 402 games ≈ 4 possessions per stint; target moves ±50–75 on a single make against a signal spanning ~15. Ceiling R² ≈ 0.01 regardless of rating quality. **The stint is the wrong unit at which to compare season-level ratings** — stating it pre-empts the question of why the obvious test was not used.

**Slope finding.** RAPM is in points/100, so a calibrated rating predicts with slope 1.0. Fitted slope **1.57** (1.99 at stint level). CV minimises in-window error, not out-of-sample calibration, and the CV curve is flat over an order of magnitude. `sweep_alpha_holdout.py` tests how much of the gap this explains. Box-score arms fail the opposite way (slopes 2.7–3.2 on unitless z-scores).

**Interpretation for Ch7:** game margin is largely team quality. PIR and Win Score reward usage, usage concentrates on strong teams' best players, so a lineup's summed box-score rating partly encodes team strength — which RAPM removes *by construction*. Testable by correlating each metric against team win percentage. **Keep the established null and the interpretation visibly separate.**

**Write it honestly and lead with the result.** Ch5 and Ch6 stand independently of this chapter.

---

## Corrections to earlier claims
- **Two player-ID schemes coexist: `P\d{6}` AND legacy `P[A-Z]{3}`.** PBCN = BELINELLI, PJDR = TEODOSIC, PCCD = DATOME, PBMT = FERNANDEZ RUDY, PKLT = HEURTEL, PLRQ = VAN ROSSOM, PCPR = SIMON, PLRU = SIMONOVIC MARKO (the known homonym), PLHI = VORONTSEVICH. **A regex gate assuming the numeric form silently dropped 27 real players**, 17 of which clear the four-cell reliability gate. Skews early-season. **Never filter player_id by format — join against `player_id_map.parquet`, which is the authority.**
- **`export_shotctx_parquet.py` joins `name`/`poss` from the floored `rapm_dash.parquet` (517 players)** instead of `player_id_map.parquet` (2,374), leaving **184 null names** in `shotctx_dash.parquet`. Benign for display (all 184 sit below the 3,000-poss floor) but wrong at source. **Not yet fixed.**
- **The verdict rule existed in two places and the documented one did not govern the dashboard.** `export_shotctx_parquet.py` recomputed the thresholds inline; the mirror ships parquet only, so that copy — not `assess_identifiability.py` — decided what Tab 2 rendered. Resolved Unit 8b via `scripts/identifiability_pins.py`. **Any future threshold or verdict logic goes in that module, nowhere else.**
- **`SHOTCTX_ALPHA = 3162` is the MODAL value across twelve fits, not a pin.** Three fits differ (see O3 item 8). **Re-fitting shot-context with `--alpha 3162` would not reproduce the artifacts** — they were fit with `--cv`, which selects per bucket.
- **`-0.994` is STRUCK and is now removed from the repo** — it survived in `tab2_shotcontext.py`'s docstring and a dead `identifiability()` function until Unit 8. Normalised, the same data gives **+0.925**. Use `assess_identifiability.py`.
- **Location thresholds CONFIRMED:** rim radius **200 cm**, corner sideline min **660 cm**, corner depth max **220 cm**. Basket at origin, centimetres, x = sideline, y = depth. Arc ≈ 675. Orientation confirmed by fitted geometry.
- **2008 relabel discrepancy (0.922) EXPLAINED.** `RIM_ACTIONS = {LAYUPMD, LAYUPATT, DUNK}` classify as at_rim **regardless of coordinates**. Those codes are absent from 2023 entirely, so a rule fitted there cannot learn the branch. **The feed's action vocabulary is not constant across the study period** — a Ch3 finding as much as Ch5.
- **PIR verified exactly** — 0 disagreements across 117,089 rows against the feed's Valuation column.
- **Boxscore `Player_ID` carries trailing whitespace** (`'P000007   '`). Any new script touching boxscore IDs must strip.
- **PIR and Win Score correlate at 0.807**, not >0.95 — report as two baselines.
- **Scoring inflation:** PIR/40 rises 15.95 → 17.80, Win Score 6.24 → 7.38. Within-season standardisation is evidenced, not default.
- **The refresh is a reproduction path, not a live cron.** 2025-26 completed 24 May; no new data in the thesis window. `refresh.yml` deleted. Documented in Ch8 §8.7.
- **`stints_ids.parquet` does NOT correspond to the RAPM designs.** 296,683 design rows vs 279,174 stints all-time. `build_rapm_design.py` re-derives stints in memory. **Live trap.**
- **Coordinate coverage is 1.000 every season.** Unmapped shooters: 0 of 610,554.

---

## Open items
- **Ch8 needs a Tab 3 section** — archetypes tab, and the Synergy tab removed from the app rather than left as a stub advertising cut work.
- **`validate_tagging.py` has not been run against the four-context taxonomy.** Predates both the removal of the situation flags and the action-code era finding. A clean pass on two pre-2015 seasons closes it. **The one piece of validation work still worth doing** — flagged in Ch9 §9.5.
- **Fix `export_shotctx_parquet.py` name join** at source (see Corrections).
- **Ch6 flag box 1:** PC2–PC4 variance shares were read from an earlier 362-player run (0.278 / 0.211 / 0.203). Only PC1 (0.310) confirmed on the final artifact. Re-read from `reports/similarity_validation.txt`.
- **Ch6 flag box 2:** Table 6.3 and any dashboard screenshot must come from the same artifact — cluster ids are run-dependent.
- **Quantify the action-code share by season** — the number behind Ch5 §5.2.5.
- **2018 boxscore gate failing** — `_MISSING.csv` gamecode 21, no `_SUCCESS`. Flagged in Ch9 §9.5; remove that item if repaired.
- **Orientation failures concentrated in 2013–14** — 0.492% overall (3,020 of 613,574) but **3.3% in 2014**, ~27× elsewhere. In Ch9 §9.1.
- **`data/landing/` unused duplicate** of root `landing/` (~99 MB). Safe to delete.
- **Grid was not widened for `eval/above_break_three`** — CV picked the ceiling, so the interior optimum is unlocated. Deliberate: the verdict is α-independent and eval is the hold-out-safe window. Report as a Ch9 limitation, do not re-fit.
---

## Carry-forward
- **Fit commands live in `docs/fit_commands.md`** — every invocation, tiered by provenance. Read it before writing Ch4 or Ch5 methods. Includes `rapm_olivo` (`--min-games 50`), which was absent from this file entirely.
- **Always `--force-signs +1,-1`** on `fit_shotctx_rapm.py`. Verified present in all 12 artifacts (`sign_off=+1`, `sign_def=-1`). Shot-context fits also need **`--cv`**, not `--alpha`; `fit_shotctx_rapm.py:183` refuses to run without one of the two. Output arg is **`--out-prefix`**, not `--out`.
- **Design stems are not uniform:** all-time is `rapm_design` + `rapm_players`; `rapm_baseline.parquet` is only the leaderboard. `dash`/`eval` use `rapm_{w}_design` + `rapm_{w}_players`.
- **Week 4 fit command** (shell history): `fit_ridge_rapm.py --prefix rapm_dash --bootstrap 500 --out rapm_dash` — default floors, **no** `--alpha` (CV chose 3162.3). `--out` takes a stem, not a path. Baseline used `--prefix rapm --alpha 1995.3 --out rapm_baseline_ci`. Full record now in `docs/fit_commands.md`.
- **`rapm_eval` was re-fit 2026-08.** The original omitted `--bootstrap` (defaults to 0), so it carried **no CIs**. Re-fit as `--prefix rapm_eval --alpha 3162.3 --bootstrap 500 --out rapm_eval` — α pinned only to reproduce the point estimates; **the methodologically relevant fact is that 3162.3 was CV-selected**. Ch7's reported metrics never needed intervals and are unaffected.
- **`RAPM_WAREHOUSE` env var** overrides the app's data dir. Local main-repo run needs it (the app defaults to `warehouse/` beside itself, i.e. the mirror layout): `RAPM_WAREHOUSE=$(pwd)/warehouse streamlit run app/streamlit_app.py`. **Do not set it in the mirror** — the default is correct there. The `# HF Spaces (Wk5)` comment on that line is stale; fix in Unit 9.
- **Three season-range conventions:** `ingest_pbp`/`ingest_shots` use `--seasons 2007-2025`; `ingest_boxscore` uses `--start/--end`; `build_rapm_design` uses `--seasons 2007:2025`. Ch9 §9.1.
- **Player map layout:** `col` is the within-block index 0..n−1; `off_offset` base 0, `def_offset` base n. `player_id_map.parquet` is **(name, season)-keyed**, up to 19 rows per player — take the most recent season's spelling for display.
- **`player_id` is a String**, never an int, and comes in **two formats** (see Corrections).
- **Composite game key:** `Season * 100000 + Gamecode`; season = `groups // 100000`.
- **Data layout:** boxscores `landing/boxscore_players/`, PBP `data/pbp_lineups/`, shots `data/shots/`, warehouse at repo root. **Mirror repo has its own layout: `requirements.txt` at root, app and `warehouse/` under `app/`.**
- **Alphas:** `DASH_ALPHA=3162.3` (overall, CV-selected, pinned in the dashboard), `rapm_baseline_ci` α = 1995.3 (pinned to reproduce Week 3), `rapm_eval` 3162.3 (CV). **`SHOTCTX_ALPHA=3162` is modal, not a pin** — per-bucket CV over the grid `1,3.16,…,3162,10000`. CV curves flat near the minimum.
- **Tagged shots:** 610,554 rows, 19 seasons, 99.89% PBP join.
- **polars `group_by` yields the key as a tuple.** Forgetting to unwrap it made every set intersection compare tuples to strings, producing a `nan` mean that then passed a `<` guard and printed a false verdict. Any nan-producing statistic needs an explicit `isfinite` branch.
- **Mirror repo local directory is `euroleague-rapm-space`** (Hugging Face-era name) while the GitHub remote is `euroleague-rapm-dashboard`. Confirmed correct via `git remote -v`; the folder name is stale, not the remote.
---

## Scripts
**O4 (new):** `build_similarity_finder.py` (vectors + neighbours; `--window`, `--buckets identified|all`, `--metric euclidean|cosine`, `--compare`), `validate_similarity.py` (T1 PCA / T2 quality contamination / T3 cross-window stability), `decide_tab3_format.py` (short-list vs archetype decision, writes `shotctx_archetypes_dash.parquet`).

**Week 6 (O3):** `tag_shots.py`, `build_shotctx_design.py`, `fit_shotctx_rapm.py`, `assess_identifiability.py`, `export_shotctx_parquet.py`, `relabel_four_bucket.py`, `derive_location_rules.py` (superseded, kept for audit), `build_player_id_map.py`.

**Unit 8b:** `identifiability_pins.py` — **single source of truth** for verdict thresholds and the pin table; exports `classify`, `published`, `borderline`, `sign_check`, `sign_note`, `drift_banner`. Imported by `assess_identifiability.py` and `export_shotctx_parquet.py`. Changing a pin means editing `PINNED_VERDICTS` with a reason and updating Ch5 in the same commit — not re-running. `shotctx_{window}.parquet` now carries `verdict` (published) and `verdict_live` (raw recompute) side by side.

**Evaluation:** `build_eval_metrics.py`, `evaluate_holdout.py` (stint), `evaluate_game.py` (primary), `sweep_alpha_holdout.py`.

**Deployment:** `refresh_dashboard.sh`, `smoke_test_dashboard.sh` (clean-venv mirror test — updated for Tab 3 and the `app/` layout; checks for the `strech` typo and any surviving `-0.994`).

**App:** `app/streamlit_app.py` (4 tabs: Leaderboard, Shot context, Archetypes, Methodology — Synergy removed), `app/tab2_shotcontext.py`, `app/tab3_archetypes.py`. `requirements.txt` pins `streamlit==1.60.0`, `pandas==2.2.3`, `pyarrow==19.0.1`, `plotly==6.8.0`, `numpy==2.5.1`.
**Deploy verified 1 Aug 2026:** clean-venv smoke test passed from the mirror root; Streamlit Cloud build succeeded; live app clicked through — Tab 3 in both "By archetype" and "By player" modes, Tab 2 with the compare toggle across both windows. Headless boot does not execute tab bodies, so the manual click-through is the only check that exercises `render()`.

## Links
- Main repo: https://github.com/Spyro1322/euroleague-rapm
- Mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard
- Live dashboard: https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Fit provenance: `docs/fit_commands.md`
- Reports: `reports/{wk6_retag,wk6_idmap,wk6_o3_full,wk6_identifiability,eval_metrics,eval_holdout,eval_game,sweep_alpha,similarity_dash_identified,similarity_dash_all,similarity_validation,tab3_format_decision}`