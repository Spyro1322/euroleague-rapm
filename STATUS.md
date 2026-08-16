# Thesis Status — Euroleague Shot-Context RAPM

_Last updated: end of Unit 9 — full draft assembled and sent to supervisor_ · **_Submission: end of August 2026_**

## NEXT: Unit 10 — feedback, defence, submission

**The complete draft has gone to the supervisor.** All nine chapters plus Appendix A are written, corrected and assembled. Every fit cited in the thesis has a recorded or determined command. The tagging taxonomy is validated exhaustively. Four figures are placed.

**Unit 10 is buffer. No new modelling, no new diagnostics, no new features.** Three separate investigations in Unit 9 each began as "one command" and each ran long. Every one of them mattered — but the remaining schedule has no room for a fourth.

**What Unit 10 contains:** supervisor feedback, the defence deck, a short live demo of the dashboard, final PDF export, submission.

---

## STATE OF THE DOCUMENT

| Ch | Topic | State |
|---|---|---|
| 1 | Introduction | RQ2 rewritten around structure and granularity; §1.5 scope-evolution table added; null named in §1.4; O4/O5 promises corrected |
| 2 | Background | 3 citations were wrong and are fixed (Karlis→Damoulaki/Ntzoufras/Pelechrinis; Engelmann 2011→2017; Grassetti authors/venue); §2.4 rewritten for the pivot; 15 verified references; Olivo positioning written |
| 3 | Data & ETL (O1) | Vocabulary-regime and tagging-provenance sections added; §3.6 rewritten from the six-bucket Week-4 text; Docker claim removed; summary dropped |
| 4 | Baseline RAPM (O2) | **No corrections needed.** Flag box deleted; §4.4 gained the luck-adjustment verification; §4.7 drafting note removed |
| 5 | Shot-context RAPM (O3) | §5.2.5 flag closed with the census table; §5.5 era caveat; §5.8 rewritten on Franks et al. and retitled "Why the asymmetry" |
| 6 | Archetypes (O4) | Jaccard interpretation corrected throughout; PC shares completed; both flag boxes resolved |
| 7 | Evaluation | **§7.8 rewritten** — de-confounding falsified, transfer decay substituted; §7.9 first bullet corrected to match |
| 8 | Dashboard (O5) | §8.3 table and new §8.3.1; §8.4, §8.5, friction record and summary cut by choice |
| 9 | Limitations | **Replaced in full.** §9.1 orientation attribution inverted; §9.3 carries the falsification; §9.4 the resolution pattern; §9.5 down to one open item |
| — | Appendix A | **New.** Tagging rules, exhaustive verification, era limitations |
| — | Abstract | Done, ~230 words, four-part structure |

**Figures:** Ch3 (at-rim instrument), Ch7 ×2 (α sweep, team-aggregate decay), Ch9 (coordinate integrity). All 16 cm, 300 dpi, greyscale-safe.

---

## UNIT 9 — the three findings that changed the thesis

Unit 9 opened with one gate: run the tagging validation before writing anything, because it was the only remaining task that could force a rewrite. It did not force a rewrite. It forced eight corrections, three of them to claims this file previously asserted as established.

### 1. The tagging validator was unusable, and the taxonomy is now exhaustively verified

`validate_tagging.py` recomputed labels via the superseded six-bucket `play_context.classify()`, read raw `data/shots/`, and selected columns absent from the warehouse schema. It would have crashed rather than passed. Replaced by **`validate_tagging_4b.py`**.

- **610,554 attempts, agreement 1.000, zero disagreements.** The rule set is **unique** among eight candidates.
- **Recovered rules: corner depth 220 cm, inclusive rim test `r <= 200`, layup/dunk codes classify at-rim directly.**
- **`relabel_four_bucket.py` implements 225 cm and a strict rim test, and produced neither shipped artifact.** Internally consistent, superseded. Its only output on disk is a 2023-only file (41,311 rows) predating the retag.
- Sampling was rejected as the primary instrument: the open risk was a population property a 100-shot sample can miss by chance.

### 2. Ch7 §7.8 was wrong — de-confounding is falsified

The previous §7.8 argued RAPM under-predicts margin *because* it de-confounds team context. **That prediction was tested and rejected.**

In-window team-aggregate correlation with win pct, 2020–2024, 90 team-seasons:
plus-minus **0.936** · rapm **0.785** · win_score **0.689** · pir **0.666**

**RAPM tracks team record BETTER than either box-score metric.** The mechanism fails.

What replaced it: **the signal is fitted to its window and does not transfer.** Frozen on 2020–2024, correlated against 2025-26:

| arm | in-window | held-out | change | Ch7 margin |
|---|---|---|---|---|
| plus-minus | 0.936 | 0.557 | **−0.379** | — |
| rapm | 0.785 | 0.510 | **−0.275** | +1.77% |
| pir | 0.666 | 0.574 | −0.092 | +2.58% |
| win_score | 0.689 | 0.712 | **+0.023** | +5.08% |

- Decay orders the arms by how directly each is derived from in-window team outcomes.
- **The held-out ordering reproduces Ch7's game-margin ranking exactly** — two independent exercises, different targets, same order.
- **n = 20 teams.** The gap between 0.712 and 0.510 is NOT statistically distinguishable. **The within-arm decay is the robust finding; the level ordering is corroborative only.** Do not overstate this in the defence.
- Olivo survives intact and narrows correctly: he compares RAPM against *raw plus-minus* (0.599 vs 0.783) and this data reproduces that direction (0.785 vs 0.936). What fails is extending his comparison to the box-score metrics, which he never tested.

### 3. at_rim is measured three different ways

The feed's action vocabulary changes three times (2008, 2015, 2017). In **2008–2014 the layup/dunk codes classify at-rim directly, making the geometric rule effectively inert** — those codes are 0.750 of two-point attempts in 2008 against an at_rim share of 0.753.

| era | instrument | at_rim share |
|---|---|---|
| 2007 | coordinates, anomalous | 0.692 |
| 2008–2014 | action code; geometry inert | 0.753 → 0.510 |
| 2015–2025 | coordinates | ~0.53–0.59 |

- **Exposure is confined to the all-time fit**: 36.6% of at_rim and 33.4% of mid_range possessions predate 2015. **`dash` (2021–2025) and `eval` (2020–2024) are definition-clean**, so identifiability, archetypes and the held-out evaluation are unaffected. **Three-point contexts unaffected everywhere.**
- **Exposure is heterogeneous, which is worse than uniform**: of 944 players rated at_rim, 276 pre-2015-only, 382 post-2015-only, 286 blended. Three estimands in one column.
- **The sharp break is 2008, not 2015.** The instruments agree almost exactly where they hand over (0.518 in 2014 against 0.512 in 2015). Do not overstate the 2015 break in the defence.
- **2007 remains unexplained.** Three mechanisms tested and rejected: rescaled frame, origin-defaulted coordinates, genuine rim excess. **The sole open item in Ch9 §9.5.**

### Other corrections this unit

- **Orientation failures are NOT concentrated in 2013–14.** They are concentrated in **2007–2010**, worst at 2007 (3.95%). **2014 is 0.134% — among the cleanest seasons.** Aggregate survives (0.468% vs 0.492% previously); the attribution did not.
- **The Jaccard index is intersection over UNION, not an overlap fraction.** Ch6 §6.4 read 1 − 0.134 as 87% turnover. Correct: ~2.4 of 10 shared, ~76% turnover. **And it strengthens the argument** — agreement is 9.4% at K=1 rising to 24% at K=10, so the head of the list is LESS stable than the tail. Shortening the list makes the claim worse, which closes the obvious rescue.
- **2018 gamecode 21 is absent from the source feed entirely** — zero play-by-play rows as well as no box score. Not a pipeline defect; repeated ingestion attempts failed for that reason. Moved from §9.5 to §9.1.
- **Docker was never used.** Reproducibility rests on pinned dependencies and `docs/fit_commands.md`.

---

## PROVENANCE — every fit now has a command

- **`rapm_eval_full`** (Ch7's headline artifact): **`--min-poss 0` is uniquely determined.** The default 500 yields 495 = `rapm_eval` (a strict subset), and the artifact contains a player at `poss = 0.0`, so `--min-poss 1` would yield 676 not 677.
- **The six `sweep_a*` fits are generated, not hand-run.** `sweep_alpha_holdout.py:110–113` builds each invocation and runs it via `subprocess`. They carry `--min-poss 0 --min-games 0`, so **the sweep shares `rapm_eval_full`'s 677-player population** — §7.5 and the main evaluation are on identical ground.
- **The `rapm_eval` re-fit reproduces to ~1e-5, not exactly.** The shot-context eval export reports `max |prior - DRAPM| = 1.1e-5` against 0.0 elsewhere. Two orders inside the assertion tolerance; moves nothing. "Unchanged" overstated it.

## CODE FIXES SHIPPED

- **`export_shotctx_parquet.py` name join FIXED at source.** Names now from `player_id_map.parquet` (2,374) rather than the floored leaderboard. Re-exported all three windows: **unnamed → 0** (was 705 / 184 / 182). Display-floor exclusions now reported separately. Sign checks pass; verdicts unchanged.
- **`tab3_archetypes.py`** — docstring carried a superseded run (0.147, +0.405, 362→118); corrected to 0.134, +0.429, 379→119. The `st.info` Jaccard conflation replaced with plain language.
- Both applied via idempotent patch scripts with assertions: `patch_export_name_join.py`, `patch_tab3_strings.py`. Mirror updated and pushed.
- **Dropped:** the "Jaccard 0.102" claim. It appears in no report, `similarity_eval_all.parquet` does not exist, so it is not recomputable. Ch6 never cited it.

---

## OPEN — carry into Unit 10

- **Supervisor feedback.** The one dependency not under your control.
- **Defence deck and dashboard demo.**
- **Final proofing pass** — table numbering (several were still Table 1.5–1.10 across Ch3–Ch5), any surviving `[-> §x]` placeholders, the duplicate Appendix A heading, Franks in the Ch2 reference list, the broken sentence in Ch8 §8.3.1.
- **Evaluation-window convention** — Table 4.3 says 2020-21 – 2024-25, Ch7 says "trained 2020–2024". Same seasons, two conventions.
- **`data/landing/` unused duplicate** (~99 MB). Safe to delete.
- **Grid not widened for `eval/above_break_three`** (α ceiling). Deliberate; Ch9 limitation; **do not re-fit.**
- Hardcoded `119` in the Tab 3 expander sits beside a computed `len(df)`. Correct now, silently wrong if the clustering is ever re-run.

---

## CARRY-FORWARD — the traps

- **Do not re-run a committed fit to "check" it.** CV curves are flat over an order of magnitude; a re-run can land on a different α and silently invalidate every quoted number.
- **Shot-context fits need `--cv`, not `--alpha`.** α is CV-selected per bucket; three of twelve differ from 3162, all three-point. `SHOTCTX_ALPHA = 3162` is **modal, not a pin**.
- **Always `--force-signs +1,-1`** on `fit_shotctx_rapm.py`. Output arg is `--out-prefix`.
- **The VERIFIED tier means "string recovered from history"** — not that the command ran or produced the cited artifact. One entry was already falsified by the filesystem.
- **Two player-ID schemes: `P\d{6}` AND legacy `P[A-Z]{3}`.** 9 of the all-time top 20 carry legacy ids. **Never filter by format; join `player_id_map.parquet`.**
- **`first_season` / `last_season` are CAREER SPANS, not fit windows.** No chapter leans on them (verified).
- **MARKO SIMONOVIC is a true homonym** — two distinct players. Do not merge.
- **Composite game key: `Season * 100000 + Gamecode`.** Gamecode alone is season-scoped and silently merges unrelated games. This is what makes the hold-out verification meaningful.
- **`stints_ids.parquet` is the design input, not `stints.parquet`.** Each stint contributes up to two rows, one per offensive team, so 279,174 stints → 296,683 design rows after filters.
- **`lineup_ok` is all-True in the committed file** and catches none of the 33 duplicated fives. Distinctness is re-derived at design time.
- **Tab 2's selector gate is compound**: `name.notna() & poss >= MIN_OVERALL_POSS`. After the name fix, exclusion happens for the right reason. Leave both conditions.
- **`RAPM_WAREHOUSE`**: local main-repo run only. **Do not set it in the mirror.**
- **Mirror carries `shotctx_dash`, `shotctx_baseline`, `shotctx_archetypes_dash` only** — not `shotctx_eval`.
- **Archetype cluster ids are run-dependent.** Table 6.3 and any screenshot must come from the same artifact. **Do not re-run `decide_tab3_format.py`** before the defence.

---

## SCRIPTS ADDED IN UNIT 9

`validate_tagging_4b.py` (supersedes `validate_tagging.py`), `team_agg_corr.py`, `team_agg_corr_holdout.py`, `patch_export_name_join.py`, `patch_tab3_strings.py`.

## LINKS
- Main repo: https://github.com/Spyro1322/euroleague-rapm
- Mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard
- Live dashboard: https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Fit provenance: `docs/fit_commands.md`
- Reports: `reports/{eval_game,sweep_alpha_holdout,team_agg_corr,team_agg_corr_holdout,validate_tagging_4b,similarity_validation,tab3_format_decision}`