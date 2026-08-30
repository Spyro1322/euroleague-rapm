# Euroleague Shot-Context RAPM

Code accompanying the MSc thesis *Shot-Context Regularized Adjusted Plus-Minus for Euroleague Basketball* (SPORTS DATA CAMPUS @UCAM, MSc in Artificial Intelligence Applied to Sports, 2026).

**Live dashboard:** https://euroleague-rapm-dashboard-aemjknb7h6acfopzdwbnjm.streamlit.app/

---

## What this is

A pipeline that reconstructs on-court lineups for every Euroleague possession from 2007-08 to 2025-26, fits ridge-regularized adjusted plus-minus, and estimates separate impact coefficients per shot context (at rim, mid-range, corner three, above-the-break three). Outputs are served through a Streamlit dashboard, *At The Buzzer*.

| Thesis objective | Where it lives |
|---|---|
| O1 — reproducible ETL | `scripts/` ingestion + `warehouse/` DuckDB views |
| O2 — baseline ridge RAPM | `fit_ridge_rapm.py` |
| O3 — shot-context RAPM | `tag_shots.py`, `fit_shotctx_rapm.py` |
| O4 — player archetypes | `tab3_archetypes.py` |
| O5 — public dashboard | `app/` |

---

## Requirements

Python 3.12. Install from the pinned file:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`requirements-frozen.txt` records the exact environment the submitted results were produced in; `BUILD_ENVIRONMENT.txt` records the interpreter and platform.

Docker is **not** used. Reproducibility rests on the pinned dependencies and on `docs/fit_commands.md`.

---

## Running the dashboard locally

```bash
streamlit run app/streamlit_app.py
```

The app reads pre-computed Parquet only — it does no fitting at runtime. Append `?view=app` to the URL to skip the landing page.

---

## Reproducing the results

Every fit cited in the thesis has a recorded command in **`docs/fit_commands.md`**, tagged at one of three provenance tiers:

- **VERIFIED** — command string recovered from shell history.
- **VERIFIED BY ENTAILMENT** — not in history, but uniquely determined by properties of the committed artifact.
- **RECONSTRUCTED** — inferred from script defaults and artifact shape.

The limitations of the VERIFIED tier are documented in that file: it means the string was recovered, not that it was confirmed to have produced the cited artifact.

### Two cautions

1. **Do not re-run a committed fit to check it.** Cross-validation curves are flat over an order of magnitude in the penalty, so a re-run can select a different α and silently invalidate quoted numbers.
2. **Archetype cluster IDs are run-dependent.** Table 6.3 and the Tab 3 screenshots come from one artifact; re-running the clustering renumbers the groups.

---

## Pipeline order

```
ingest → warehouse.pbp_clean → stints_ids.parquet
       → build_rapm_design.py    → design matrix
       → fit_ridge_rapm.py       → baseline (O2)
       → tag_shots.py            → 610,554 tagged attempts
       → fit_shotctx_rapm.py     → per-context fits (O3)
       → export_shotctx_parquet.py → dashboard artifacts
```

Validation and evaluation scripts sit alongside: `validate_lineups.py`, `validate_tagging_4b.py`, `sweep_alpha_holdout.py`, `build_eval_metrics.py`, `team_agg_corr.py`.

Written reports for each are under `reports/`.

---

## Things a reader should know before modifying anything

These are non-obvious and each one caused a bug during development.

- **Composite game key is `Season * 100000 + Gamecode`.** Gamecode alone is season-scoped and will silently merge unrelated games.
- **`stints_ids.parquet` is the design input**, not `stints.parquet`. Each stint contributes up to two rows, one per offensive team.
- **`lineup_ok` is all-True in the committed file** and catches none of the duplicated fives; distinctness is re-derived at design time.
- **Shot-context fits require `--cv`, not `--alpha`** — the penalty is CV-selected per bucket. `SHOTCTX_ALPHA = 3162` is the modal value, not a pin.
- **Always pass `--force-signs +1,-1`** to `fit_shotctx_rapm.py`.
- **`first_season` / `last_season` are career spans, not fit windows.**
- **2018 gamecode 21 is absent from the source feed entirely** — no play-by-play, no box score. Not a pipeline defect.
- **Identifiability verdicts have one source of truth:** `identifiability_pins.py`, imported by both `assess_identifiability.py` and `export_shotctx_parquet.py`.

---

## Known limitations in the code

- The above-break-three evaluation fit selected the ceiling of the α grid. The grid was deliberately not widened; this is discussed as a limitation in Chapter 9 and the fit should not be re-run.
- A hardcoded count in the Tab 3 expander sits beside a computed length. Correct for the committed clustering artifact, silently wrong if the clustering is re-run.

---

## Data

Raw play-by-play is retrieved from the Euroleague API via `euroleague_api` 0.1.1. Three bugs in that wrapper are worked around in the ingestion layer; see `docs/`. Derived Parquet and NPZ artifacts are not included in this archive due to size — the pipeline regenerates them, subject to the cautions above.

---

## Repositories

- Pipeline: https://github.com/Spyro1322/euroleague-rapm
- Deployment mirror: https://github.com/Spyro1322/euroleague-rapm-dashboard

The mirror carries only the dashboard and its three Parquet artifacts; Streamlit Community Cloud watches it.