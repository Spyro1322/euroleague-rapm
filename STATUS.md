# Thesis Status — Euroleague Shot-Context RAPM

_Last updated: Unit 10 — supervisor feedback received, no changes requested_ · **_Submission: end of August 2026_**

## NEXT: Unit 10 — defence and submission

**Supervisor feedback received. No changes to the document.** All nine chapters plus Appendix A stand as reviewed. Every objective is delivered or descoped with reasons on record. Every fit cited has a recorded or determined command. The tagging taxonomy is exhaustively verified. The scientific content is closed.

**The proofing pass is complete.** Table numbering, `[-> §x]` placeholders, the duplicate Appendix A heading, the Franks reference, the Ch8 §8.3.1 sentence and the evaluation-window convention are all resolved. Ch8 now describes the landing page, so the chapter and the deployed app agree.

**What remains is the defence deck and submission.** No modelling, no new diagnostics, no new features. The dashboard is finished and verified on Community Cloud; nothing further should be added to it before the defence.

**The risk profile is now entirely schedule.** Nothing left can fail in a way that forces a rewrite, and nothing left depends on anyone else.

---

## OPEN — everything that remains

### Defence
- **Deck and dashboard demo.** Use `?view=app` in slides to skip the landing screen during a live demo.
- **Screenshots must come from the deployed mirror, not localhost.** Ch8 now describes the landing page, so the screenshots and the chapter have to agree — retake them if the app changes again.
- **Final PDF export and submission.**

### Housekeeping
- `data/landing/` unused duplicate (~99 MB). Safe to delete.
- **Grid not widened for `eval/above_break_three`** (α ceiling). Deliberate; Ch9 limitation; **do not re-fit.**
- Hardcoded `119` in the Tab 3 expander sits beside a computed `len(df)`. Correct now, silently wrong if the clustering is ever re-run.

---

## STATE OF THE DOCUMENT

| Ch | Topic | State |
|---|---|---|
| 1 | Introduction | RQ2 rewritten around structure and granularity; §1.5 scope-evolution table added; null named in §1.4; O4/O5 promises corrected |
| 2 | Background | 3 citations were wrong and are fixed (Karlis→Damoulaki/Ntzoufras/Pelechrinis; Engelmann 2011→2017; Grassetti authors/venue); §2.4 rewritten for the pivot; 15 verified references; Olivo positioning written; Franks added to the reference list |
| 3 | Data & ETL (O1) | Vocabulary-regime and tagging-provenance sections added; §3.6 rewritten from the six-bucket Week-4 text; Docker claim removed; summary dropped |
| 4 | Baseline RAPM (O2) | **No corrections needed.** Flag box deleted; §4.4 gained the luck-adjustment verification; §4.7 drafting note removed |
| 5 | Shot-context RAPM (O3) | §5.2.5 flag closed with the census table; §5.5 era caveat; §5.8 rewritten on Franks et al. and retitled "Why the asymmetry" |
| 6 | Archetypes (O4) | Jaccard interpretation corrected throughout; PC shares completed; both flag boxes resolved |
| 7 | Evaluation | **§7.8 rewritten** — de-confounding falsified, transfer decay substituted; §7.9 first bullet corrected to match |
| 8 | Dashboard (O5) | §8.3 table and new §8.3.1; §8.4, §8.5, friction record and summary cut by choice; §8.3.1 now covers the landing page |
| 9 | Limitations | **Replaced in full.** §9.1 orientation attribution inverted; §9.3 carries the falsification; §9.4 the resolution pattern; §9.5 down to one open item |
| — | Appendix A | Tagging rules, exhaustive verification, era limitations; duplicate heading removed |
| — | Abstract | Done, ~230 words, four-part structure |

**Figures:** Ch3 (at-rim instrument), Ch7 ×2 (α sweep, team-aggregate decay), Ch9 (coordinate integrity). All 16 cm, 300 dpi, greyscale-safe.

---

## THE NUMBERS TO HAVE AT HAND FOR THE DEFENCE

### The evaluation null
Box-score metrics outperform RAPM on game-margin prediction, over naive:
**Win Score +5.08% · PIR +2.58% · RAPM +1.77%**

CV-selected α (3162.3) yields calibration slope ~3.88. Perfect calibration (slope 1.04 at α=100) is the **worst-performing** arm. Calibration and accuracy are in direct opposition along the regularisation path — report both.

### Why RAPM loses: transfer, not de-confounding
The original mechanism (RAPM under-predicts margin *because* it de-confounds team context) **was tested and falsified.** In-window team-aggregate correlation with win pct, 2020–2024, 90 team-seasons: plus-minus **0.936** · rapm **0.785** · win_score **0.689** · pir **0.666**. RAPM tracks team record *better* than either box-score metric.

Replacement: **the signal is fitted to its window and does not transfer.**

| arm | in-window | held-out | change | Ch7 margin |
|---|---|---|---|---|
| plus-minus | 0.936 | 0.557 | **−0.379** | — |
| rapm | 0.785 | 0.510 | **−0.275** | +1.77% |
| pir | 0.666 | 0.574 | −0.092 | +2.58% |
| win_score | 0.689 | 0.712 | **+0.023** | +5.08% |

- Decay orders the arms by how directly each is derived from in-window team outcomes.
- The held-out ordering **reproduces Ch7's game-margin ranking exactly** — two independent exercises, different targets, same order.
- **n = 20 teams.** The gap between 0.712 and 0.510 is NOT statistically distinguishable. **The within-arm decay is the robust finding; the level ordering is corroborative only. Do not overstate this.**
- Olivo survives intact and narrows correctly: he compares RAPM against *raw plus-minus* (0.599 vs 0.783) and this data reproduces that direction (0.785 vs 0.936). What fails is extending his comparison to box-score metrics, which he never tested.

### Identifiability
Two-point contexts identified (at_rim ~0.478, mid_range ~0.350 correlation, stable across windows). Three-point contexts **not** identified. `above_break_three`'s near-threshold correlation is carried by a wrong-sign defensive coefficient, and CV selected the grid ceiling for that fit — three independent lines of evidence for the NONE verdict.

### Tagging
**610,554 attempts, agreement 1.000, zero disagreements.** The rule set is **unique** among eight candidates. Recovered rules: corner depth 220 cm, inclusive rim test `r <= 200`, layup/dunk codes classify at-rim directly. Sampling was rejected as the primary instrument — the open risk was a population property a 100-shot sample can miss by chance.

### at_rim is measured three different ways
| era | instrument | at_rim share |
|---|---|---|
| 2007 | coordinates, anomalous | 0.692 |
| 2008–2014 | action code; geometry inert | 0.753 → 0.510 |
| 2015–2025 | coordinates | ~0.53–0.59 |

- **Exposure is confined to the all-time fit**: 36.6% of at_rim and 33.4% of mid_range possessions predate 2015. **`dash` (2021–2025) and `eval` (2020–2024) are definition-clean.** Three-point contexts unaffected everywhere.
- **Exposure is heterogeneous, which is worse than uniform**: of 944 players rated at_rim, 276 pre-2015-only, 382 post-2015-only, 286 blended. Three estimands in one column.
- **The sharp break is 2008, not 2015.** Instruments agree almost exactly at handover (0.518 in 2014 vs 0.512 in 2015). **Do not overstate the 2015 break.**
- **2007 remains unexplained.** Three mechanisms tested and rejected. The sole open item in Ch9 §9.5.
- **Orientation failures are concentrated in 2007–2010**, worst at 2007 (3.95%) — **not** 2013–14. 2014 is 0.134%, among the cleanest seasons.

### Archetypes (O4)
Cluster membership survives cross-window replication: **adjusted Rand index +0.429 at k=5**, stable k=3–7. Individual similarity does not: **Jaccard@10 = 0.134** — about 2.4 of ten neighbours shared, ~76% turnover, on windows sharing four of five seasons. Agreement is 9.4% at K=1 rising to 24% at K=10, so **the head of the list is less stable than the tail** — shortening the list makes the claim worse, which closes the obvious rescue.

---

## DASHBOARD — closed this unit

Live on Streamlit Community Cloud, verified rendering. Branding: **At The Buzzer — Advanced Analytics Platform**.

- **Landing page** (`app/landing.py`): logo, one-paragraph intro, entry gate via `?view=app`. Includes `home_button()` because **Streamlit writes query params with `history.replaceState`, not `pushState` — browser back cannot return to the landing page.** Not a bug in the module.
- **`.streamlit/config.toml` committed to BOTH repos.** `toolbarMode = "minimal"` removes the Deploy button and dev menu server-side, which is what stops the chrome flashing on load. Pinned light theme (`base = "light"`) so the navy/orange logo reads and Ch8 screenshots don't depend on the viewer's OS setting.
- **Status widget ("running man") has no config equivalent** — removed by `_hide_chrome()` CSS on `[data-testid="stStatusWidget"]`.
- **Logo**: Canva design `DAHSV9rvd74`. Canva free plan blocks transparent-background PNG export, so `scripts/strip_logo_bg.py` samples the corner colour, knocks out the ground, trims the margin and writes `atb_lockup.png` / `atb_mark_512.png` / `atb_icon_64.png` to `app/assets/`.
- **Logo is base64-inlined** in the landing page — Streamlit will not serve a local file to an `<img src>` inside `st.markdown` unless static serving is enabled.
- **Tab 2 radar**: radial tick labels moved off the horizontal axis (`angle=45`, `showline=False`); footnote margin fixed.
- **Tab 3**: title/legend collision fixed in both figures. Legend needed `yanchor="top"` — anchored to bottom it grows upward into the title.
- **Streamlit CSS caution**: `stMarkdownContainer` paragraph rules beat inherited `text-align`, so centring must be declared per-element with `!important`.

---

## PROVENANCE

- **`rapm_eval_full`** (Ch7's headline artifact): **`--min-poss 0` is uniquely determined.** The default 500 yields 495 = `rapm_eval` (a strict subset), and the artifact contains a player at `poss = 0.0`, so `--min-poss 1` would yield 676 not 677.
- **The six `sweep_a*` fits are generated, not hand-run.** `sweep_alpha_holdout.py:110–113` builds each invocation and runs it via `subprocess`. They carry `--min-poss 0 --min-games 0`, so **the sweep shares `rapm_eval_full`'s 677-player population** — §7.5 and the main evaluation are on identical ground.
- **The `rapm_eval` re-fit reproduces to ~1e-5, not exactly.** The shot-context eval export reports `max |prior - DRAPM| = 1.1e-5` against 0.0 elsewhere. Two orders inside the assertion tolerance; moves nothing.
- **Fit commands** are documented in `docs/fit_commands.md` at three tiers: VERIFIED (shell history confirmed), VERIFIED BY ENTAILMENT (implied by artifact properties), RECONSTRUCTED.

---

## CARRY-FORWARD — the traps

- **Do not re-run a committed fit to "check" it.** CV curves are flat over an order of magnitude; a re-run can land on a different α and silently invalidate every quoted number.
- **The VERIFIED tier means "string recovered from history"** — not that the command ran or produced the cited artifact. One entry was already falsified by the filesystem.
- **Shot-context fits need `--cv`, not `--alpha`.** α is CV-selected per bucket; three of twelve differ from 3162, all three-point. `SHOTCTX_ALPHA = 3162` is **modal, not a pin**.
- **Always `--force-signs +1,-1`** on `fit_shotctx_rapm.py`. Output arg is `--out-prefix`.
- **Two player-ID schemes: `P\d{6}` AND legacy `P[A-Z]{3}`.** 9 of the all-time top 20 carry legacy ids. **Never filter by format; join `player_id_map.parquet`.**
- **`first_season` / `last_season` are CAREER SPANS, not fit windows.** No chapter leans on them (verified).
- **MARKO SIMONOVIC is a true homonym** — two distinct players. Do not merge.
- **Composite game key: `Season * 100000 + Gamecode`.** Gamecode alone is season-scoped and silently merges unrelated games. This is what makes the hold-out verification meaningful.
- **`stints_ids.parquet` is the design input, not `stints.parquet`.** Each stint contributes up to two rows, one per offensive team, so 279,174 stints → 296,683 design rows after filters.
- **`lineup_ok` is all-True in the committed file** and catches none of the 33 duplicated fives. Distinctness is re-derived at design time.
- **`2018 gamecode 21` is absent from the source feed entirely** — zero play-by-play rows and no box score. Not a pipeline defect.
- **Docker was never used.** Reproducibility rests on pinned dependencies and `docs/fit_commands.md`.
- **Tab 2's selector gate is compound**: `name.notna() & poss >= MIN_OVERALL_POSS`. Leave both conditions.
- **`RAPM_WAREHOUSE`**: local main-repo run only. **Do not set it in the mirror.**
- **Mirror carries `shotctx_dash`, `shotctx_baseline`, `shotctx_archetypes_dash` only** — not `shotctx_eval`.
- **Archetype cluster ids are run-dependent.** Table 6.3 and any screenshot must come from the same artifact. **Do not re-run `decide_tab3_format.py`** before the defence.
- **`.streamlit/config.toml` must exist in the MIRROR**, not just main. Community Cloud reads the mirror. Config changes need a full app reboot; they do not hot-reload.

---

## SCRIPTS

**Unit 9:** `validate_tagging_4b.py` (supersedes `validate_tagging.py`), `team_agg_corr.py`, `team_agg_corr_holdout.py`, `patch_export_name_join.py`, `patch_tab3_strings.py`

**Unit 10:** `app/landing.py`, `scripts/strip_logo_bg.py`

## LINKS
- Main repo: https://github.com/Spyro1322/euroleague-rapm
- Mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard
- Live dashboard: https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/
- Olivo thesis: https://amslaurea.unibo.it/id/eprint/30803/1/olivo_thesis.pdf
- Canva logo design: `DAHSV9rvd74`
- Fit provenance: `docs/fit_commands.md`
- Reports: `reports/{eval_game,sweep_alpha_holdout,team_agg_corr,team_agg_corr_holdout,validate_tagging_4b,similarity_validation,tab3_format_decision}`