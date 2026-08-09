# Thesis Status — Euroleague Shot-Context RAPM

_Last updated: end of Unit 7 (Ch4 + Ch7 drafted; model spec verified from source)_ · **_Submission: end of August 2026_**

## NEXT: Unit 9 — corrections, appendices, read-through, send to supervisor
**Ch4 and Ch7 are drafted.** All four previously-unwritten chapters now exist. What remains is correction, citation, cross-referencing and two pieces of new prose (abstract, tagging-rule appendix).

**Run `validate_tagging.py` FIRST, before any Unit 9 writing.** It is the only remaining task that can return a result requiring a rewrite. A clean pass closes a Ch9 limitation; a failure qualifies Ch5's taxonomy and propagates to Ch6 and the appendix. Discovering that after the read-through is expensive. Two pre-2015 seasons — that is where the action-code vocabulary gap and the 2013–14 orientation concentration both sit. **Check it targets the four-context taxonomy before trusting a pass** — the script predates the retag and may still compare against the seven old play types.

**Unit 9 order:** validate_tagging → Ch8 Tab 3 section → Ch1/Ch3 corrections → Ch2 citations → Ch5 §5.8 → Ch6 flag boxes → tagging-rule appendix (after validation) → abstract → cross-reference pass → full read-through → **send to supervisor at the close of Unit 9**. Unit 10 is buffer — no new features.

**Writing is the binding constraint. No new modelling.**

---

## UNIT 7 — Ch4 and Ch7 drafted; model specification verified from source
Both chapters were written from artifacts and source, not from this file. **That process found this file wrong in eight places.** Corrections are listed under "Corrections" below; the model specification recovered is recorded here.

### Verified model specification (read from source + design artifacts)
- **`y` is offensive points per 100 possessions, NOT point differential.** Each row is one team's offensive possessions. `build_rapm_design.py:8`.
- **The design is UNSIGNED.** All ten non-zeros per row are `+1` — five attackers in the offensive block, five defenders in the defensive block. There is no `−1`. Necessarily so: `w_col = X.T @ w` recovers possessions, which would cancel under a ±1 encoding.
- **Sign convention is applied AFTER fitting:** `drapm = -coef[n_players:]` in `fit_ridge_rapm.py`. Positive DRAPM = good defence.
- **`w` is possessions**, not stint length in seconds.
- **`poss` in leaderboards counts BOTH ENDS** (`w_col[:n] + w_col[n:]`). Per-end is half. Tavares 14,893 → 7,446 offensive → **73.6 poss/40min**, matching published Euroleague pace. `MIN_POSS = 500` is therefore ~250 offensive possessions, 3–4 games. Permissive.
- **Design dimensions:** all-time 296,683 × 4,366, nnz 2,966,830 = **exactly 10 per row, no exceptions**. Density 0.229%. 4,366 = 2 × 2,183 players.
- **`ALPHAS = np.logspace(1.5, 4.5, 16)`** → 31.6 … 31,623. **Both reported α values are grid points**: 1995.3 is k=9, 3162.3 is k=10. Neither was hand-chosen.
- **`GroupKFold(n_splits=5)`** on the composite game key. No game split across folds.
- **Bootstrap seed 42**, B configurable, `--bootstrap` defaults to 0.
- **`--min-games` defaults to 0.** The leaderboard gate is possession-only. The `n_games` min of 5 is incidental, not enforced.
- **`out_stem = args.out or f"{args.prefix}_baseline"`** (`fit_ridge_rapm.py:113`).

### LUCK ADJUSTMENT — specified and VERIFIED ACTIVE
Was undocumented anywhere; recovered from `build_rapm_design.py:64–75, 144–152` and verified against the committed design.

- **Three-point outcomes only.** Two-point and free-throw points pass through as realised. Expected total = `non3_pts + 3 × 3pa × lg_3p_pct`.
- **League rate, not player rate** — a player-specific rate would reintroduce the shooting variance the adjustment removes.
- **Season-specific: 19 distinct values.** 0.3605 (2007) → trough ~0.3355 (2010) → 0.3653 (2023) → 0.3590 (2025). A pooled rate would have introduced an era artefact.
- **Applied inside the design build, before the per-100 scaling** — therefore **upstream of `select_alpha`**. The CV-selected α corresponds to the target actually fitted. This concern is closed, not flagged.
- **Verification (no log survives; `LOG.info` went to stderr and was not captured):** recovering per-row points as `y * w / 100` gives **51.2% fractional rows**. Sample values reconstruct the formula exactly at the 2007 rate: `2.163 = 3 × 2 × 0.3605`, `5.244 = 2 + 3 × 3 × 0.3605`, `8.163 = 6 + 3 × 2 × 0.3605`. The ~49% integer rows are stints with no three-point attempt. **Record in `docs/fit_commands.md` at VERIFIED BY ENTAILMENT with this arithmetic as the basis.**
- **Describe as "three-point luck-adjusted", not "luck-adjusted"** — the adjustment is partial and the chapter says so.

---

## Chapter status
| Ch | Topic | State |
|---|---|---|
| 1 | Introduction | drafted — O3 relabel "play-type"→"shot-context"; O4 flag; scope-evolution section |
| 2 | Background | drafted — needs three-point repeatability citation (Ch5 §5.8) **and Olivo citation for Ch7 §7.8** |
| 3 | Data & ETL (O1) | drafted — corrections below; **add the Olivo game-count agreement (see O1 corroboration)** |
| 4 | Baseline RAPM (O2) | **DRAFTED — 9 pp, 1 flag box (STATUS/provenance corrections only)** |
| 5 | Shot-context RAPM (O3) | drafted, 10 pp — §5.8 gains Unit 8b sign + grid-ceiling evidence |
| 6 | Shot-context archetypes (O4) | drafted, ~5 pp, 2 flag boxes |
| 7 | Evaluation | **DRAFTED — 7 pp, 3 tables, 1 flag box (team-aggregate correlation)** |
| 8 | Dashboard (O5) | drafted — **needs Tab 3 section**; deploy verified 1 Aug |
| 9 | Limitations & future work | drafted, ~5 pp, 1 flag box |

Non-chapter, still unwritten: **abstract** (must lead with the null) and **tagging-rule appendix**.

---

## CH7 RESULT — the null, and the sweep that failed to rescue it
Train 2020–2024, hold-out 2025-26, frozen scaling, 402 games. Naive arm = **fitted home-advantage constant, +3.77 pts** (within published Euroleague range — a harness sanity check worth stating).

| arm | RMSE | vs naive | corr | winner | R² | slope |
|---|---|---|---|---|---|---|
| win_score | 11.604 | **+5.08%** | 0.322 | 65.4% | 0.099 | 3.19 |
| pir | 11.910 | +2.58% | 0.268 | 63.4% | 0.051 | 2.70 |
| rapm | 12.009 | +1.77% | 0.226 | 63.2% | 0.035 | **1.57** |
| shotctx | 12.064 | +1.32% | 0.216 | 64.4% | 0.026 | 1.43 |
| naive | 12.225 | — | — | 63.4% | 0 | — |

**THE ALPHA SWEEP OVERTURNS THE OBVIOUS EXPLANATION.** I had assumed over-shrinkage caused the 1.57 slope and that a smaller α would fix both calibration and accuracy. `reports/sweep_alpha_holdout.json` shows the opposite — **calibration and accuracy are in direct opposition**:

| α | rating sd | RMSE | vs naive | corr | slope |
|---|---|---|---|---|---|
| 100 | 4.295 | 12.984 | −6.20% | 0.131 | **1.04** |
| 316 | 2.918 | 12.615 | −3.19% | 0.154 | 1.13 |
| 1,000 | 1.820 | 12.265 | −0.32% | 0.191 | 1.28 |
| **3,162 (CV)** | 1.021 | 12.009 | +1.77% | 0.226 | 1.57 |
| 10,000 | 0.512 | 11.882 | +2.81% | 0.246 | 2.19 |
| 31,620 | 0.226 | **11.840** | **+3.15%** | 0.252 | 3.88 |

- **Perfect calibration (slope 1.04) is the WORST arm in the thesis** (−6.20% vs naive).
- **Best RMSE is the worst-calibrated** (slope 3.88), with rating sd collapsed to 0.226.
- Correlation rises monotonically with α → the extra spread at low α is **estimation noise, not signal**. Heavy shrinkage is a noise filter.
- **Gap decomposition:** optimal α raises RAPM from +1.77% to +3.15%, **overtaking PIR** but still trailing Win Score. That closes **1.39 of the 3.32-point gap (42%)**; **1.93 points are not attributable to α**. The null survives its own best correction.
- **α = 31,620 is the CV grid ceiling (31,623).** The hold-out optimum is the largest value CV could ever have returned; CV chose an order of magnitude below it. Boundary solution, interior optimum unlocated, carried as a Ch9 limitation — do not widen and re-fit.
- The best-predicting configuration has **0.23 pts/100 spread across 677 players**. Whatever predicts margin, it is not individual player differences.

**Common support (73 games), full table now recorded** — both RAPM arms post **negative R²**:
| arm | RMSE | vs naive | corr | winner | R² |
|---|---|---|---|---|---|
| win_score | 11.456 | +10.76% | 0.452 | 65.8% | 0.204 |
| pir | 11.632 | +9.39% | 0.424 | 67.1% | 0.179 |
| naive | 12.837 | — | — | 67.1% | 0 |
| rapm | 13.055 | −1.69% | 0.122 | 65.8% | −0.034 |
| shotctx | 13.070 | −1.81% | 0.082 | 58.9% | −0.037 |

**Do not lean on this subset**, three reasons: 73 games is noise; the criterion is gated by the box-score arms' narrower coverage (453 vs RAPM's 677); and **naive RMSE is higher here (12.837 vs 12.225), so it is a different population — these games have wider margins.** That last point is new and supports the Ch7 §7.8 mechanism.

**Ch7 §7.8 mechanism now has external support.** Olivo reports **RAPM–team-record correlation 0.599 against raw plus-minus 0.783**. He frames it as RAPM's virtue (less confounded by team context); Ch7 reaches the same property from the other side (that de-confounding is what costs it on margin prediction). Same mechanism, opposite valence, published independently before this evaluation existed.

**Still open (Ch7's only flag):** correlate each arm's **team-aggregated** rating against team win pct on 2020–2024. Olivo establishes the adjusted-vs-unadjusted gap; what remains is showing PIR/Win Score sit on the unadjusted side. One command, data already in the warehouse.

**Arm provenance:** `evaluate_game.py` defaults `--rapm-stem rapm_eval` (495 floored) but the reported figures match **`rapm_eval_full` (677)** — RMSE matches the sweep to five decimals and coverage 76.3% is that artifact's. `eval_game.json` stores no stem field. Record in `fit_commands.md` at VERIFIED BY ENTAILMENT. `--shotctx-window` defaults to `eval` (confirmed, hold-out safe).

**Stint-level is a structural null** — <0.11% improvement, R² ≈ 0.002, 14,067 stints, ~4 poss/stint, ceiling R² ≈ 0.01 regardless of rating quality. Olivo independently states Euroleague stints run ~3 possessions — **cite him**, it removes the argument's reliance on my own arithmetic alone.

---

## CH4 RESULT — Olivo comparison is 6/10, not 10/10
**The "10/10 replication passed" claim in previous STATUS versions was wrong.** Corrected against the actual PDF.

**Window matches exactly:** Olivo 2018-19→2022-23; `rapm_olivo_design` groups = [2018 2019 2020 2021 2022], 87,334 rows, 240 rated after `--min-games 50` + `MIN_POSS`.

**Which table to compare against matters.** Olivo reports three fits. His headline (Table 4.10) is **Elastic Net** — not comparable. Table 3.3 is plain ridge, unsplit. **The structurally comparable fit is his Table 4.3** (weighted ridge, O/D split, λ=185.2). Overlap: **6/10 vs Table 4.3**, 8/10 vs Table 3.3, 10 of his top 15 vs Table 4.10. **Do not compare λ across implementations** (glmnet vs sklearn, different standardisation). Scale differs ~2.5–3× — compare ranks, not values.

**Three-tier finding, and the third tier is the good one:**
1. **Samples agree exactly.** Every overlapping player matches on game count — Tavares 173, Walkup 174, Fernandez 138, Simon 125, DiBartolomeo 133, Mirotic 128, Clyburn 124, Abrines 112, Fall 108, Balbay 101, Ukhov 66, Canaan 63, Exum 63, Sorkin 58. One exception: Sanli 133 vs his 132. **This is independent external corroboration of O1 — put it in Ch3.**
2. **Top three match in near-identical order** (Tavares/Fernandez/Campazzo vs his Campazzo/Tavares/Fernandez).
3. **The four misses are demoted, not absent, and they separate cleanly on possessions.** Balbay 35, Canaan 33, Sorkin 56, Ukhov 72 of 240 — all still top-third. **Agreed players: 6,708–14,893 poss. Demoted players: 2,137–4,386. No overlap.** Olivo's own §4.3.3 funnel-effect section predicts exactly this: his 50-game gate screens games, not minutes, and he flags Balbay (8 min/game) himself. Agreement is complete among well-estimated players and breaks down precisely where both authors say estimation is unreliable.

**Comparability caveats to state, both of which make the agreement harder to obtain:** his weighting is stint length × game type × game phase, mine is possessions; **he fits raw points, I fit three-point luck-adjusted**.

**Limitation:** Olivo publishes only top-10/top-15 tables, so **no rank correlation over the shared population is computable**. Top-N overlap is the only available statistic.

**Also citable from Olivo:** his possession-weighted RAPM alternative (his Table 4.2) shows max divergence <0.1 pts/100 from the simple sum — **justifies using `RAPM = ORAPM + DRAPM` without re-deriving it.**

### Leaderboard: bootstrap intervals do not mean what they appear to
**Interval width RISES with possessions.** `corr(width, log poss) = +0.484`. Quartile medians: 3.495 / 4.391 / 4.904 / 4.625 against median poss 788 / 1,774 / 4,044 / 11,009. Median width 4.466.

Mechanism: thin players are shrunk hard, so their coefficient barely moves across resamples — **the narrowness records the strength of the penalty, not the precision of the estimate.** Heavy-possession players escape the penalty and are free to move. The q4 easing is genuine precision reasserting (Calathes, 37,343 poss, width 3.67).

Two consequences:
- **Width is not a reliability measure and must not be presented as one.**
- **Sorting by `RAPM_lo` would make the thin-player problem WORSE**, since the same shrinkage that narrows a thin interval props up its lower bound.

Same pattern as Ch7 §7.7: the penalty suppresses apparent variation and it looks like quality. Both diagnostics only appear when you compare across the possession range.

**Thin-player artefacts in the all-time top 20:** GOREE, MARCUS ranks 11th on **25 games, one season (2007)**, 2,035 poss. ILYASOVA 5th on 52 games. Presented unchanged with intervals visible, used as the worked example for §4.6.2 rather than re-floored.

---

## Corrections to earlier claims
**New this unit:**
- **`rapm_baseline_ci.parquet` DOES NOT EXIST.** `fit_commands.md` records the committed all-time fit with `--out rapm_baseline_ci` at **VERIFIED** tier; no such file is on disk. The artifact is `warehouse/rapm_baseline.parquet` — what the same command produces with `--out` omitted (default stem `{prefix}_baseline`). **The VERIFIED tier certifies that a string was recovered from history, not that the command ran or produced the cited artifact.** `grep | sort -u` collects typed commands indiscriminately. Fix the entry; keep the tier definition in mind for every other entry.
- **`first_season` / `last_season` are CAREER SPANS, not fit windows.** Populated from `player_id_map.parquet`, unaffected by the design. The Olivo fit (2018–2022) reports Tavares as 2017–2025. **These are exactly the columns a reader consults to ask what data produced a rating, and they do not answer it.** Check Ch5/Ch6 do not lean on them.
- **The Olivo fit's window was never recorded** anywhere. It is 2018–2022, read from the design's `groups`. Record it with the fit.
- **`y` is offensive points, not differential; the design is unsigned; `w` is possessions; `poss` counts both ends.** See "Verified model specification".
- **The luck adjustment is three-point-only, league-rate, season-specific, and ACTIVE.** Was entirely undocumented. See above.
- **Both α values are grid points**, not hand-chosen. `logspace(1.5, 4.5, 16)`.
- **Olivo comparison is 6/10 against his comparable table**, not 10/10.

**Carried forward, unchanged:**
- **Two player-ID schemes: `P\d{6}` AND legacy `P[A-Z]{3}`.** PBCN=BELINELLI, PJDR=TEODOSIC, PCCD=DATOME, PBMT=FERNANDEZ RUDY, PKLT=HEURTEL, PLRQ=VAN ROSSOM, PCPR=SIMON, PLRU=SIMONOVIC MARKO (homonym), PLHI=VORONTSEVICH, PJKO=DIAMANTIDIS, PBWL=LORBEK, PATW=PAPALOUKAS. **9 of the all-time top 20 carry legacy ids** — a regex gate would delete half the headline table. **Never filter by format; join `player_id_map.parquet`.**
- **`export_shotctx_parquet.py` joins name/poss from floored `rapm_dash.parquet` (517)** instead of the id map (2,374) → **184 null names** in `shotctx_dash.parquet`. 701 − 517 = 184, arithmetic confirmed. Benign for display; wrong at source. **Not yet fixed.**
- **Verdict logic lives ONLY in `scripts/identifiability_pins.py`.** The export used to recompute inline and the mirror ships parquet only, so that copy governed the dashboard. Resolved Unit 8b.
- **`SHOTCTX_ALPHA = 3162` is MODAL, not a pin.** Three of twelve fits differ, all three-point buckets. Re-fitting with `--alpha 3162` would not reproduce them; shot-context needs `--cv`.
- **`-0.994` is STRUCK and removed.** Normalised, the same data gives +0.925.
- **Location thresholds CONFIRMED:** rim 200 cm, corner sideline min 660 cm, corner depth max 220 cm. Arc ≈ 675.
- **2008 relabel discrepancy EXPLAINED.** `RIM_ACTIONS = {LAYUPMD, LAYUPATT, DUNK}` classify as at_rim regardless of coordinates, and are absent from 2023 entirely. **The feed's action vocabulary is not constant across the study period** — a Ch3 finding as much as Ch5.
- **PIR verified exactly** — 0 disagreements across 117,089 rows.
- **Boxscore `Player_ID` carries trailing whitespace** (`'P000007   '`).
- **PIR and Win Score correlate at 0.807**, not >0.95 — two baselines.
- **Scoring inflation:** PIR/40 15.95 → 17.80, Win Score 6.24 → 7.38. Within-season standardisation is evidenced, not default.
- **The refresh is a reproduction path, not a live cron.** `refresh.yml` deleted. Ch8 §8.7.
- **`stints_ids.parquet` does NOT correspond to the RAPM designs.** 296,683 design rows vs 279,174 stints. `build_rapm_design.py` re-derives stints in memory. **Live trap.**
- **Coordinate coverage is 1.000 every season.** 0 of 610,554 unmapped.

---

## Open items
- **`validate_tagging.py` has not been run against the four-context taxonomy.** **Run FIRST in Unit 9.** Two pre-2015 seasons. Verify it targets four contexts, not seven play types.
- **Ch7 flag:** team-aggregated rating vs team win pct, 2020–2024, all arms. One command.
- **Ch8 needs a Tab 3 section.**
- **Fix `export_shotctx_parquet.py` name join** at source.
- **Ch6 flag 1:** PC2–PC4 variance shares read from an earlier 362-player run. Re-read from `reports/similarity_validation.txt`.
- **Ch6 flag 2:** Table 6.3 and any dashboard screenshot must come from the same artifact — cluster ids are run-dependent.
- **Quantify the action-code share by season** — the number behind Ch5 §5.2.5.
- **2018 boxscore gate failing** — `_MISSING.csv` gamecode 21, no `_SUCCESS`. Ch9 §9.5.
- **Orientation failures concentrated in 2013–14** — 0.492% overall, **3.3% in 2014**, ~27× elsewhere. Ch9 §9.1.
- **`data/landing/` unused duplicate** (~99 MB). Safe to delete.
- **Grid not widened for `eval/above_break_three`** (α ceiling). Deliberate; Ch9 limitation, do not re-fit.
- **Update `docs/fit_commands.md`:** correct the `rapm_baseline_ci` stem; add the Olivo window; add the luck-adjustment entailment; add the `rapm_eval_full` stem entailment.

---

## Carry-forward
- **Fit commands live in `docs/fit_commands.md`** — tiered by provenance. **The VERIFIED tier means "string recovered from history", not "command ran and produced this artifact".** One entry has already been falsified by the filesystem.
- **Always `--force-signs +1,-1`** on `fit_shotctx_rapm.py`; also needs `--cv`, not `--alpha`. Output arg is `--out-prefix`.
- **Design stems are not uniform:** all-time is `rapm_design` + `rapm_players`; `rapm_baseline.parquet` is only the leaderboard. `dash`/`eval` use `rapm_{w}_design` + `rapm_{w}_players`.
- **Do not re-run a committed fit to "check" it.** CV curves are flat over an order of magnitude; a re-run can land on a different α and silently invalidate every quoted number.
- **`RAPM_WAREHOUSE` env var** overrides the app's data dir. Local main-repo run: `RAPM_WAREHOUSE=$(pwd)/warehouse streamlit run app/streamlit_app.py`. **Do not set it in the mirror.** The `# HF Spaces (Wk5)` comment is stale; fix in Unit 9.
- **Three season-range conventions:** `ingest_pbp`/`ingest_shots` use `--seasons 2007-2025`; `ingest_boxscore` uses `--start/--end`; `build_rapm_design` uses `--seasons 2007:2025`. Ch9 §9.1.
- **Player map layout:** `col` is the within-block index 0..n−1; `off_offset` base 0, `def_offset` base n. `player_id_map.parquet` is **(name, season)-keyed** — take the most recent season's spelling.
- **Composite game key:** `Season * 100000 + Gamecode`; season = `groups // 100000`. Gamecode alone is season-scoped and silently merges unrelated games.
- **Alphas:** `DASH_ALPHA = 3162.3`, `rapm_baseline` α = 1995.3, `rapm_eval` 3162.3. All grid points on `logspace(1.5, 4.5, 16)`.
- **Tagged shots:** 610,554 rows, 19 seasons, 99.89% PBP join.
- **polars `group_by` yields the key as a tuple.** Any nan-producing statistic needs an explicit `isfinite` branch.
- **Mirror local directory is `euroleague-rapm-space`** (HF-era name); remote is `euroleague-rapm-dashboard`. Folder name is stale, not the remote.
- **`HISTTIMEFORMAT` is now set** — future provenance recovery will carry timestamps.

---

## Scripts
**Baseline (O2):** `build_rapm_design.py`, `fit_ridge_rapm.py`, `build_player_id_map.py`.

**Week 6 (O3):** `tag_shots.py`, `build_shotctx_design.py`, `fit_shotctx_rapm.py`, `assess_identifiability.py`, `export_shotctx_parquet.py`, `relabel_four_bucket.py`, `derive_location_rules.py` (superseded), `validate_tagging.py` (**not yet run against four contexts**).

**Unit 8b:** `identifiability_pins.py` — single source of truth for verdict thresholds. Any future threshold logic goes here, nowhere else.

**O4:** `build_similarity_finder.py`, `validate_similarity.py`, `decide_tab3_format.py`.

**Evaluation:** `build_eval_metrics.py`, `evaluate_holdout.py` (stint), `evaluate_game.py` (primary), `sweep_alpha_holdout.py`.

**Deployment:** `refresh_dashboard.sh`, `smoke_test_dashboard.sh`.

**App:** `app/streamlit_app.py` (4 tabs: Leaderboard, Shot context, Archetypes, Methodology — Synergy removed), `app/tab2_shotcontext.py`, `app/tab3_archetypes.py`.

## Links
- Main repo: https://github.com/Spyro1322/euroleague-rapm
- Mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard
- Live dashboard: https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Fit provenance: `docs/fit_commands.md`
- Reports: `reports/{eval_game,eval_holdout,sweep_alpha_holdout,similarity_validation,tab3_format_decision,wk6_*}`