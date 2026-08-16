# Thesis Status — Euroleague Shot-Context RAPM

_Last updated: end of Unit 9 (all chapters corrected; tagging validated; provenance closed)_ · **_Submission: end of August 2026_**

## NEXT: send to supervisor, then Unit 10 — feedback, defence, submission

**Every chapter is drafted and corrected. Every fit cited in the thesis has a recorded or determined command. The tagging taxonomy is validated exhaustively.** What remains before sending is a read-through of the assembled document; what remains after is supervisor feedback, the defence deck, and the PDF.

**Unit 10 is buffer. No new features, no new modelling, no new diagnostics.** Three separate investigations in Unit 9 each began as "one command" and each ran long. The remaining schedule has no room for a fourth.

---

## BEFORE SENDING — read-through only

Three classes of problem exist only in the assembled document and cannot be caught chapter by chapter.

**Seams.** Eight drop-ins were written independently. The era-dependence finding now appears in Appendix A, Ch3, Ch5 §5.5, Ch5 §5.7 and Ch9 §9.1. Layering is intended; near-identical sentences across five locations are not.

**Numbering.** Ch1 §1.5 → §1.6 shifts everything after it. Ch9 gained a subsection. Ch4's `[→ §7.x]` placeholders resolve here. **Ch4 §4.1, §4.3 and §4.7 are cross-referenced by Ch5 and Ch6 — treat those numbers as fixed.**

**Appendix collision.** Ch5's Appendix 5.A duplicates Appendix A's threshold statement. **Cut 5.A to a pointer.** Two appendices stating the same thresholds is exactly how the 220-vs-225 discrepancy would be reintroduced.

**One consistency check.** The thesis now argues a negative headline in three places — the abstract, Ch7 §7.8, and Ch9 §9.3. They must agree in emphasis. §7.8 was rewritten last and is the most likely to be out of step.

---

## UNIT 9 — what changed, and what it cost

Unit 9 opened with a single gate: run `validate_tagging.py` before any writing, because it was the only remaining task that could force a rewrite. It did not force a rewrite. It forced eight corrections, three of them to claims this file previously asserted as established.

### The gate: tagging validation

`validate_tagging.py` was **unusable** — it recomputes labels via the superseded six-bucket `play_context.classify()`, reads raw `data/shots/`, and selects columns absent from the warehouse schema. Replaced by **`validate_tagging_4b.py`**, which validates the shipped artifact exhaustively rather than by sampling.

- **610,554 attempts, agreement 1.000, zero disagreements.** The rule set is **unique** among eight candidates.
- **Recovered rules: corner depth 220 cm, inclusive rim test `r ≤ 200`, layup/dunk codes classify at-rim directly.** These are `play_context.py`'s constants with flag precedence removed.
- **`relabel_four_bucket.py` implements 225 cm and a strict rim test, and produced neither shipped artifact.** It is internally consistent and superseded. Its only output on disk is a single-season file predating the retag.
- Sampling was rejected as the primary instrument: the open risk was the action-code vocabulary gap, which is a population property a 100-shot sample can miss by chance.

### Three claims in this file were wrong

1. **Orientation failures are NOT concentrated in 2013–14.** They are concentrated in **2007–2010**, worst at 2007 (3.95%; 10.93% of threes inside the arc). **2014 is 0.134% — among the cleanest seasons.** The aggregate (0.468% here vs 0.492% previously) survives; the attribution did not. Ch9 §9.1 rewritten.
2. **The de-confounding account of the Ch7 null is FALSIFIED.** See below.
3. **`rapm_baseline_ci.parquet` does not exist** — carried forward correctly from Unit 7, now corrected in `fit_commands.md`.

### THE BIG ONE — Ch7 §7.8 was wrong and is rewritten

The previous §7.8 argued RAPM under-predicts margin *because* it de-confounds team context, and that the box-score arms are rewarded for retaining it. **That prediction was tested and rejected.**

In-window team-aggregate correlation with win pct, 2020–2024, 90 team-seasons:

| arm | corr |
|---|---|
| plus-minus | 0.936 |
| **rapm** | **0.785** |
| win_score | 0.689 |
| pir | 0.666 |

**RAPM tracks team record BETTER than either box-score metric.** The mechanism fails.

What replaced it: **the signal is fitted to its window and does not transfer.** Frozen on 2020–2024, correlated against 2025-26:

| arm | in-window | held-out | change | Ch7 margin |
|---|---|---|---|---|
| plus-minus | 0.936 | 0.557 | **−0.379** | — |
| rapm | 0.785 | 0.510 | **−0.275** | +1.77% |
| pir | 0.666 | 0.574 | −0.092 | +2.58% |
| win_score | 0.689 | 0.712 | **+0.023** | +5.08% |

- **Decay orders the arms by how directly each is derived from in-window team outcomes.**
- **The held-out ordering reproduces Ch7's game-margin ranking exactly** — two independent exercises, different targets, same order.
- **n = 20 teams.** The gap between 0.712 and 0.510 is NOT statistically distinguishable. **The within-arm decay is the robust finding; the level ordering is corroborative only.** Do not overstate this.
- Olivo's result survives intact and narrows correctly: he compares RAPM against *raw plus-minus* (0.599 vs 0.783) and this data reproduces that direction (0.785 vs 0.936). What fails is extending his comparison to the box-score metrics, which he never tested.

Scripts: `team_agg_corr.py`, `team_agg_corr_holdout.py`. Reports in `reports/`.

### New finding — at_rim is measured three different ways

The feed's action vocabulary changes three times (2008, 2015, 2017), and in **2008–2014 the layup/dunk codes classify at-rim directly, making the geometric rule effectively inert**: those codes are 0.750 of two-point attempts in 2008 against an at-rim share of 0.753.

| era | instrument | at_rim share |
|---|---|---|
| 2007 | coordinates, anomalous | 0.692 |
| 2008–2014 | action code; geometry inert | 0.753 → 0.510 |
| 2015–2025 | coordinates | ≈0.53–0.59 |

- **Exposure is confined to the all-time fit**: 36.6% of at_rim and 33.4% of mid_range possessions predate 2015. **`dash` (2021–2025) and `eval` (2020–2024) are definition-clean**, so the identifiability verdicts, archetypes and held-out evaluation are unaffected. **Three-point contexts are unaffected in every window.**
- **Exposure is heterogeneous, which is worse than uniform**: of 944 players rated at_rim, 276 are pre-2015-only, 382 post-2015-only, 286 blended. **Three estimands in one column.** All-time two-point figures are descriptive, not a ranking.
- **2007 anomaly is unexplained.** Three mechanisms tested and rejected: rescaled frame (threes sit within a few per cent of modern positions), origin-defaulted coordinates (0.18% at origin, *lower* than 2008), genuine rim excess (10.4% within 50 cm vs ~8%). What remains is a season-specific recording convention. **Carried as the sole open item in Ch9 §9.5.**

### Ch6 — a Jaccard misreading

**The Jaccard index is intersection over UNION, not an overlap fraction.** §6.4 read 1 − 0.134 as 87% turnover. Correct: ~2.4 of 10 shared, ~76% turnover. Conclusion unaffected; number wrong.

**And it strengthens the argument.** In shared-member terms agreement is 9.4% at K=1 rising to 24% at K=10 — **the head of the list is LESS stable than the tail.** Shortening the list makes the claim worse, which closes off the obvious rescue ("just report the top three"). The old "flat in K" framing left that open.

Tables 6.1, 6.2, 6.3 verified against the deployed artifact; PC shares 31.0 / 28.1 / 20.9 / 20.0 unchanged from the earlier 362-player run to within rounding. Flags 1 and 3 closed.

### Provenance — every fit now has a command

- **`rapm_eval_full`** (Ch7's headline artifact) had no recorded command. **`--min-poss 0` is now uniquely determined**: the default 500 yields 495 = `rapm_eval` (a strict subset), and the artifact contains a player at `poss = 0.0`, so `--min-poss 1` would yield 676 not 677.
- **The six `sweep_a*` fits are generated, not hand-run.** `sweep_alpha_holdout.py:110–113` builds each invocation and runs it via `subprocess`. **They carry `--min-poss 0 --min-games 0`, so the sweep shares `rapm_eval_full`'s 677-player population** — §7.5 and the main evaluation are on identical ground.
- **The `rapm_eval` re-fit reproduces to ~1e-5, not exactly.** The shot-context eval export reports `max |prior − DRAPM| = 1.1e-5` against exactly 0.0 elsewhere, because those fits carry `mu` from the original fit while the leaderboard on disk is the re-fit. Two orders inside the 1e-4 assertion tolerance; moves nothing. "Unchanged" overstated it.

### Code fixes shipped

- **`export_shotctx_parquet.py` name join FIXED at source.** Names now come from `player_id_map.parquet` (2,374) rather than the floored leaderboard. Re-exported all three windows: **unnamed → 0** (was 705 / 184 / 182). Display-floor exclusions now reported separately. Sign checks pass; verdicts unchanged.
- **`tab3_archetypes.py`** — docstring carried a superseded run (0.147, +0.405, 362→118); corrected to 0.134, +0.429, 379→119. The `st.info` Jaccard conflation replaced with plain language.
- Both applied via idempotent patch scripts with assertions: `patch_export_name_join.py`, `patch_tab3_strings.py`.
- **Dropped:** the "Jaccard 0.102" claim for three-point inclusion. It appears in no report, `similarity_eval_all.parquet` does not exist, so it is not recomputable. Ch6 never cited it.

### 2018 ingestion — resolved as an upstream gap

Gamecode 21 in 2018 returns **zero play-by-play rows as well as no box score**. It is absent from the source feed entirely, not a pipeline defect — which is why repeated ingestion attempts failed. The previous claim that "its play-by-play data is unaffected" was wrong. Moved from Ch9 §9.5 (unverified) to §9.1 (data availability).

---

## Chapter status — all drafted and corrected

| Ch | Topic | State |
|---|---|---|
| 1 | Introduction | corrected — RQ2 rewritten, scope-evolution §1.5 added, null named in §1.4 |
| 2 | Background | corrected — 3 citations wrong (Karlis→Damoulaki/Ntzoufras/Pelechrinis; Engelmann 2011→2017; Grassetti authors), §2.4 rewritten for the pivot, 15 verified references |
| 3 | Data & ETL (O1) | corrected — vocabulary regimes + tagging provenance sections added |
| 4 | Baseline RAPM (O2) | **no corrections needed.** Flag box deletable — both items now recorded in `fit_commands.md` |
| 5 | Shot-context RAPM (O3) | corrected — §5.2.5 flag closed, §5.5 era caveat, §5.8 rewritten on Franks et al. |
| 6 | Archetypes (O4) | corrected — Jaccard interpretation, PC shares, both flag boxes resolved |
| 7 | Evaluation | **§7.8 rewritten** — de-confounding falsified, transfer decay substituted |
| 8 | Dashboard (O5) | corrected — §8.3 table rows, new §8.3.1 on regions-not-rankings |
| 9 | Limitations | **replaced in full** — §9.1, §9.2, §9.3, §9.4, §9.5, §9.6 all changed |
| — | Appendix A | **new** — shot-context tagging rules, verification, era limitations |
| — | Abstract | done |

---

## Open items

- **Ch9 §9.5 must drop to ONE item.** Delete the provenance bullet; move the 2018 game to §9.1. The 2007 coordinate anomaly is the only genuine open item.
- **Ch5 Appendix 5.A** — cut to a pointer at Appendix A.
- **Read-through**: seams, numbering, the three negative-headline statements.
- **`data/landing/` unused duplicate** (~99 MB). Safe to delete.
- **Grid not widened for `eval/above_break_three`** (α ceiling). Deliberate; Ch9 limitation; **do not re-fit.**
- Hardcoded `119` in the Tab 3 expander sits beside a computed `len(df)`. Correct now, silently wrong if the clustering is ever re-run. Not worth changing before submission.

---

## Carry-forward — the traps

- **Do not re-run a committed fit to "check" it.** CV curves are flat over an order of magnitude; a re-run can land on a different α and silently invalidate every quoted number.
- **Shot-context fits need `--cv`, not `--alpha`.** α is CV-selected per bucket; three of twelve differ from 3162, all three-point. `SHOTCTX_ALPHA = 3162` is **modal, not a pin**.
- **Always `--force-signs +1,-1`** on `fit_shotctx_rapm.py`. Output arg is `--out-prefix`.
- **The VERIFIED tier means "string recovered from history"** — not that the command ran or produced the cited artifact. One entry was already falsified by the filesystem.
- **Two player-ID schemes: `P\d{6}` AND legacy `P[A-Z]{3}`.** 9 of the all-time top 20 carry legacy ids. **Never filter by format; join `player_id_map.parquet`.**
- **`first_season` / `last_season` are CAREER SPANS, not fit windows.** They cannot answer what data produced a rating. No chapter leans on them (verified).
- **MARKO SIMONOVIC is a true homonym** — two distinct players (`PLRU` 1986 SF; `P012711` 1999 C). Do not merge.
- **Composite game key: `Season * 100000 + Gamecode`**; season = `groups // 100000`. Gamecode alone silently merges unrelated games.
- **`stints_ids.parquet` does NOT correspond to the RAPM designs** — 296,683 design rows vs 279,174 stints. `build_rapm_design.py` re-derives in memory. Live trap.
- **Design stems are not uniform**: all-time uses `rapm_design` + `rapm_players`; `dash`/`eval` use `rapm_{w}_design` + `rapm_{w}_players`.
- **Verdict logic lives ONLY in `scripts/identifiability_pins.py`.**
- **Tab 2's selector gate is compound**: `name.notna() & poss >= MIN_OVERALL_POSS`. After the name fix, exclusion happens for the right reason (display floor), not the wrong one (missing identity). Leave both conditions in place.
- **`RAPM_WAREHOUSE`**: local main-repo run only. **Do not set it in the mirror.**
- **Mirror carries `shotctx_dash`, `shotctx_baseline`, `shotctx_archetypes_dash` only** — not `shotctx_eval`.
- **Archetype cluster ids are run-dependent.** Table 6.3 and any screenshot must come from the same artifact. Do not re-run `decide_tab3_format.py`.
- **Three season-range conventions** across `ingest_pbp`/`ingest_shots`, `ingest_boxscore`, `build_rapm_design`.

---

## Scripts added in Unit 9

`validate_tagging_4b.py` (supersedes `validate_tagging.py`), `team_agg_corr.py`, `team_agg_corr_holdout.py`, `patch_export_name_join.py`, `patch_tab3_strings.py`.

## Links
- Main repo: https://github.com/Spyro1322/euroleague-rapm
- Mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard
- Live dashboard: https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Fit provenance: `docs/fit_commands.md`
- Reports: `reports/{eval_game,sweep_alpha_holdout,team_agg_corr,team_agg_corr_holdout,validate_tagging_4b,similarity_validation,tab3_format_decision}`