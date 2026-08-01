# Fit commands — provenance record

Source of the exact invocations behind every model fit cited in the thesis.
Ch4 (baseline RAPM), Ch5 (shot-context RAPM) and Ch7 (evaluation) all reference
fits whose commands existed only in shell history; this file is that record.

**Recovered 2026-08 from `~/.bash_history` via**
`grep -h "fit_ridge_rapm\|fit_shotctx_rapm" ~/.bash_history | sort -u`

**Provenance is marked per command.** Three tiers are used, and they are not
interchangeable:

- **VERIFIED** — the command string itself was recovered from shell history.
- **VERIFIED BY ENTAILMENT** — the command was not recovered, but every argument
  is either read from a fit artifact or forced by the script's argument parser.
- **RECONSTRUCTED** — inferred from notes only. Nothing in this file currently
  sits at this tier; do not add anything to it without saying so explicitly.

---

## VERIFIED — recovered verbatim from shell history

### Committed fits (the three the thesis reports)

| stem | command | notes |
|---|---|---|
| `rapm_baseline_ci` | `python scripts/fit_ridge_rapm.py --prefix rapm --bootstrap 500 --alpha 1995.3 --out rapm_baseline_ci` | All-time 2007–2025. **α pinned, not CV-selected** — reproduces the validated Week 3 fit. 500 bootstrap resamples for the leaderboard CIs. |
| `rapm_dash` | `python scripts/fit_ridge_rapm.py --prefix rapm_dash --bootstrap 500 --out rapm_dash` | Current-form 2021–2025. **No `--alpha`** — CV selected 3162.3. Default floors. Dashboard default window. |
| `rapm_eval` | **superseded — see below** | Hold-out-safe 2020–2024, 2025-26 fully excluded. |

**`rapm_eval` was re-fit and the artifact on disk no longer matches history.**

Original, from shell history:

```
python scripts/fit_ridge_rapm.py --prefix rapm_eval --out rapm_eval
```

No `--alpha` (CV selected 3162.3) and no `--bootstrap`, which defaults to 0 — so
that fit carried **no credible intervals**. Re-fit 2026-08 to add them, with α
pinned to the value CV had already selected:

```
python3 scripts/fit_ridge_rapm.py --prefix rapm_eval --alpha 3162.3 --bootstrap 500 --out rapm_eval
```

Point estimates are unchanged (same α, same design, seed 42); intervals added.
**The methodologically relevant fact for Ch7 is that α = 3162.3 was CV-selected,
not chosen** — the pin in the re-fit exists only to reproduce the original
point estimates, not as a modelling decision.

### Replication fit (Ch4 validation — absent from STATUS.md before this file)

```
python scripts/fit_ridge_rapm.py --prefix rapm_olivo --min-games 50 --bootstrap 0
```

The Olivo (2024) like-for-like comparison fit. `--min-games 50` is the
distinguishing argument and does not appear in any other invocation — it matches
Olivo's inclusion criterion rather than this project's possession floors.
Ch4's replication section depends on this command; it was undocumented until now.
Worth stating explicitly in the chapter that the comparison fit used a
deliberately different inclusion gate from the rest of the project.

### Pipeline / scratch fits (no `--out`, wrote to the default stem)

```
python scripts/build_player_id_map.py && python scripts/build_rapm_design.py && python scripts/fit_ridge_rapm.py --bootstrap 0
python scripts/build_rapm_design.py && python scripts/fit_ridge_rapm.py --bootstrap 0
python scripts/fit_ridge_rapm.py --bootstrap 0
python scripts/fit_ridge_rapm.py --alpha 3162.3 --bootstrap 0
```

Exploratory. None carries `--out`, so each overwrote the default stem. **Do not
cite these in the thesis** — the artifact any one of them produced has since
been overwritten by the next. Retained only to show the sequence of design
rebuilds that preceded the committed fits.

---

## VERIFIED BY ENTAILMENT — shot-context fits (Ch5, O3)

`grep` returned **no shell-history matches for `fit_shotctx_rapm`**. The commands
below were not recovered. Every argument, however, is either read directly from a
fit artifact or forced by the argument parser, so the reconstruction is not
guesswork. Only the interpreter spelling (`python` vs `python3`) is unknowable,
and it does not affect the result.

```
python3 scripts/fit_shotctx_rapm.py --window baseline --cv --force-signs +1,-1
python3 scripts/fit_shotctx_rapm.py --window dash --cv --force-signs +1,-1
python3 scripts/fit_shotctx_rapm.py --window eval --cv --force-signs +1,-1
```

| argument | basis |
|---|---|
| `--force-signs +1,-1` | **verified from artifacts**: `sign_off=+1`, `sign_def=-1` in all 12 fits (4 buckets × 3 windows) |
| `--cv` | **entailed**: α varies per bucket (1000 / 3162 / 10000), which `--alpha` cannot produce since it pins one value for all buckets. `fit_shotctx_rapm.py:183` refuses to run without one of the two, so no third path exists |
| default `--alpha-grid` | **entailed**: every selected α is a point on `1,3.16,10,31.6,100,316,1000,3162,10000` |
| `--window` | **entailed**: `--prefix` defaults to `shotctx_{window}`, matching the artifact filenames |
| no `--out-prefix` | **entailed**: `--out-prefix` defaults to the input prefix, and outputs carry it |

### α is CV-selected per bucket, NOT pinned

| window | at_rim | mid_range | corner_three | above_break_three |
|---|---|---|---|---|
| baseline | 3162 | 3162 | **1000** | 3162 |
| dash | 3162 | 3162 | 3162 | 3162 |
| eval | 3162 | 3162 | **1000** | **10000** |

Every deviation from 3162 is a three-point bucket; no two-point bucket moved in
any window. `STATUS.md`'s `SHOTCTX_ALPHA = 3162` is the **modal** value across
the twelve fits, not a pin. **Do not re-fit with `--alpha 3162`** — it would fail
to reproduce `baseline/corner_three` (1000), `eval/corner_three` (1000), or
`eval/above_break_three` (10000).

### `eval/above_break_three` selected the grid ceiling — a Ch5 result

10000 is the largest α in the default grid, so this is a **boundary solution**:
CV asked for the most heavily regularised model available, and
`fit_shotctx_rapm.py:271` warns in exactly this case that the optimum may lie
outside the grid. Maximum shrinkage means the per-bucket estimate is pulled as
far as possible toward the prior — which is the same claim as "no recoverable
individual effect", reached by a route entirely independent of the correlation
test.

That makes **three independent lines of evidence** for the `NONE` verdict on
above-break threes:

1. magnitude — |corr| = 0.046 / 0.098 / 0.046 across the three windows, below the 0.10 threshold
2. sign — the largest correlation is `corr_def` **positive** in all three windows, the wrong direction for a real defensive effect (at_rim and mid_range are negative everywhere)
3. regularisation — CV selects the grid maximum in the eval window

It also accounts for two diagnostics that otherwise look anomalous: that fit's
low `dev_sd` (0.309 against 0.734 / 0.761 elsewhere) and eval being the only
window with an ambiguous normalised-separation result (+0.353 vs +0.925 / +0.982).
Both follow from 10× more shrinkage on one bucket.

**Verdicts are computed on unshrunk coefficients and are α-independent**, so none
of this moves the identifiability result. The grid was not widened to locate the
interior optimum — Ch9 §9.x.

Cross-reference: `--force-signs`' own help text gives the justification —
*per-bucket calibration is noise-driven on thin buckets*. That design decision
was made before the identifiability result and is independently vindicated by
it, `corner_three` (11k attempts) being the clearest case.

---

## Gaps and cautions

**1. `rapm_eval` credible intervals — RESOLVED.** `--bootstrap` defaults to 0
(`fit_ridge_rapm.py:103`) and the original eval command omitted the flag, so that
fit carried point estimates only. Ch7's reported metrics (RMSE, correlation, R²,
calibration slope) do not require intervals, so nothing was invalidated. The
artifact has since been re-fit with `--alpha 3162.3 --bootstrap 500`, and now
carries them. An eval-window leaderboard with error bars is drawable from the
current artifact but was **not** drawable from the one the original evaluation
ran against.

**2. Ordering is not recoverable.** `HISTTIMEFORMAT` was unset, so entries carry
no timestamps, and `sort -u` discarded whatever file order remained. The sequence
of scratch fits above is therefore not evidence of the order in which they ran.
Any claim of the form "X was fit before Y" needs artifact mtimes, not this file.

**3. `--prefix` refers to a design stem, and stems are not uniform.** All-time
uses `rapm_design` + `rapm_players` while `rapm_baseline.parquet` is only the
leaderboard; `dash`/`eval` use `rapm_{w}_design` + `rapm_{w}_players`. So
`--prefix rapm` and `--prefix rapm_dash` are not parallel constructions, and
`--out` takes a stem rather than a path. The shot-context script uses
`--out-prefix`, not `--out`.

**4. Do not re-run a committed fit to "check" it.** `rapm_baseline_ci` is pinned
at α = 1995.3 precisely so it reproduces Week 3. `rapm_dash` and `rapm_eval` let
CV choose, and the CV curve is flat over an order of magnitude — a re-run can
legitimately land on a different α and silently invalidate every number the
thesis quotes, including the pinned `DASH_ALPHA = 3162.3` in the dashboard.

The shot-context fits carry the same hazard in a different form: they are
CV-selected **per bucket**, so re-running them requires `--cv`, not a pinned α.
Passing `--alpha 3162` would produce twelve uniform fits where the committed
artifacts have three exceptions, and would erase the grid-ceiling result above.

**5. Preserve history going forward.** So a future gap does not require this
exercise again:

```
echo 'export HISTTIMEFORMAT="%F %T "' >> ~/.bashrc
echo 'export HISTSIZE=50000' >> ~/.bashrc
echo 'export HISTFILESIZE=50000' >> ~/.bashrc
```