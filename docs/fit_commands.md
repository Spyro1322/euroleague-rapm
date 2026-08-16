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
| `rapm_baseline` | `python scripts/fit_ridge_rapm.py --prefix rapm --bootstrap 500 --alpha 1995.3` | All-time 2007–2025. **α pinned, not CV-selected** — reproduces the validated Week 3 fit. 500 bootstrap resamples for the leaderboard CIs. **See the correction below: the recovered string carried `--out rapm_baseline_ci`, and no such artifact exists.** |
| `rapm_dash` | `python scripts/fit_ridge_rapm.py --prefix rapm_dash --bootstrap 500 --out rapm_dash` | Current-form 2021–2025. **No `--alpha`** — CV selected 3162.3. Default floors. Dashboard default window. |
| `rapm_eval` | **superseded — see below** | Hold-out-safe 2020–2024, 2025-26 fully excluded. |

### CORRECTION — the all-time entry was falsified by the filesystem

The string recovered from history ended `--out rapm_baseline_ci`. **No
`rapm_baseline_ci.parquet` exists on disk.** The committed artifact is
`warehouse/rapm_baseline.parquet`, which is what the same command produces with
`--out` omitted, since `out_stem` defaults to `f"{prefix}_baseline"`
(`fit_ridge_rapm.py:113`).

This is the reason the VERIFIED tier is defined as it is. **The tier certifies
that a string was recovered from shell history — not that the command ran, nor
that it produced the artifact cited beside it.** `grep | sort -u` collects typed
commands indiscriminately, including ones that were typed and then edited,
abandoned, or superseded. Every other VERIFIED entry in this file carries the
same exposure and should be checked against the filesystem before being cited.

Ch4 cites the artifact on disk and is unaffected.

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

Point estimates reproduce to approximately 1e-5 (same α, same design, seed 42);
intervals added. **Not bit-identical** — exporting the shot-context eval window
reports `max |prior − DRAPM| = 1.1e-5` against exactly 0.0 for the baseline and
dash windows, because the shot-context fits carry `mu` from the original
`rapm_eval` while the leaderboard on disk is the re-fit one. The difference is
two orders of magnitude inside the export's 1e-4 assertion tolerance and moves
no reported figure, but "unchanged" overstates it.
**The methodologically relevant fact for Ch7 is that α = 3162.3 was CV-selected,
not chosen** — the pin in the re-fit exists only to reproduce the original
point estimates, not as a modelling decision.

### Replication fit (Ch4 validation — absent from STATUS.md before this file)

```
python scripts/fit_ridge_rapm.py --prefix rapm_olivo --min-games 50 --bootstrap 0
```

**Estimation window: 2018–2022** (i.e. 2018-19 through 2022-23), read from the
design's own `groups` vector — 87,334 rows, five seasons, matching Olivo exactly.
The window was recorded nowhere before this entry, and **cannot be read from the
output artifact**: `first_season` / `last_season` are career spans taken from
`player_id_map.parquet` and are unaffected by the design, so the Olivo fit reports
Tavares as 2017–2025. Those are precisely the columns a reader would consult to
ask what data produced a rating, and they do not answer it.

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

## VERIFIED BY ENTAILMENT — the evaluation artifact Ch7 actually consumes

**No command string for `rapm_eval_full` was recovered from shell history**, and
it is the artifact behind Ch7's headline table. Every argument has since been
determined from the artifact itself, so the entry sits at this tier rather than
in the gaps list.

`evaluate_game.py` defaults `--rapm-stem rapm_eval`, but the figures reported in
Ch7 match **`rapm_eval_full`**: RMSE agrees with the α sweep to five decimals and
the 76.3% coverage is that artifact's, not `rapm_eval`'s. `eval_game.json` stores
no stem field, so the run cannot be identified from its own output — it is
identified from the artifact's contents instead.

| property | `rapm_eval` | `rapm_eval_full` |
|---|---|---|
| players rated | **495**, floored at the default 500 possessions | **677**, unfloored |
| CI columns | `RAPM_lo` / `RAPM_hi` present | **absent** |
| consumed by | leaderboard display | **Ch7 evaluation** |
| relationship | a strict subset of `rapm_eval_full` | superset |

### Command recovered by entailment — the floor argument is uniquely determined

```
python3 scripts/fit_ridge_rapm.py --prefix rapm_eval --alpha 3162.3 \
    --bootstrap 0 --min-poss 0 --out rapm_eval_full
```

| argument | basis |
|---|---|
| `--min-poss 0` | **uniquely determined.** `--min-poss` is a real flag (`fit_ridge_rapm.py:105`) defaulting to `MIN_POSS = 500` and applied at line 163. The default yields 495 — exactly `rapm_eval`, whose ids are a strict subset of this artifact's. `rapm_eval_full` contains a player at `poss = 0.0`, so `--min-poss 1` would yield 676, not 677. Only 0 produces 677. |
| `--bootstrap 0` | entailed by the absence of `RAPM_lo` / `RAPM_hi` (the parser default) |
| `--alpha 3162.3` | entailed by agreement with the sweep to five decimals. **Under-determined against `--cv`**: CV selects 3162.3 on this design, so both invocations produce identical output. The value is certain; the flag is not. |
| `--out rapm_eval_full` | entailed by the filename — the default stem would be `rapm_eval_baseline` |

The two evaluation artifacts therefore differ by the possession floor alone. Ch4
§4.7 documents that distinction correctly, and Ch7 §7.2 needs no disclaimer.

**One observation, not a provenance issue.** A player with `poss = 0.0` is
present in the unfloored artifact. They contribute nothing to any aggregate, but
the coverage figure Ch7 quotes is computed over this population and includes
them.

---

## VERIFIED BY ENTAILMENT — the luck adjustment

Undocumented anywhere before this entry. Recovered from
`build_rapm_design.py:64–75, 144–152` and verified against the committed design.

- **Three-point outcomes only.** Two-point and free-throw points pass through as
  realised. Expected total = `non3_pts + 3 × 3pa × lg_3p_pct`.
- **League rate, not player rate** — a player-specific rate would reintroduce the
  shooting variance the adjustment exists to remove.
- **Season-specific**, 19 distinct values: 0.3605 (2007) → trough ≈0.3355 (2010)
  → 0.3653 (2023) → 0.3590 (2025). A pooled rate would have introduced an era
  artefact.
- **Applied inside the design build, before per-100 scaling**, therefore upstream
  of `select_alpha`. The CV-selected α corresponds to the target actually fitted.

**Verification (no log survives; `LOG.info` went to stderr and was not captured).**
Recovering per-row points as `y * w / 100` gives **51.2% fractional rows**. Sample
values reconstruct the formula exactly at the 2007 rate:
`2.163 = 3 × 2 × 0.3605`, `5.244 = 2 + 3 × 3 × 0.3605`,
`8.163 = 6 + 3 × 2 × 0.3605`. The ~49% integer rows are stints with no three-point
attempt.

Describe in the thesis as **"three-point luck-adjusted"**, not "luck-adjusted" —
the adjustment is partial and Ch4 §4.4 says so.

---

## VERIFIED — the penalty sweep (Ch7 §7.5)

Six artifacts `sweep_a{100,316,1000,3162,10000,31620}.parquet` back the sweep
table. They are **generated, not hand-run**: `sweep_alpha_holdout.py` constructs
each invocation and executes it through `subprocess`, so the script's source is
the provenance record and is stronger than shell history.

```
python3 scripts/sweep_alpha_holdout.py --alphas 100,316,1000,3162,10000,31620
```

Per-fit form, read verbatim from `sweep_alpha_holdout.py:110–113`:

```
python3 scripts/fit_ridge_rapm.py --prefix rapm_eval --alpha {alpha} \
    --min-poss 0 --min-games 0 --bootstrap 0 --out sweep_a{int(alpha)}
```

**The sweep shares `rapm_eval_full`'s population.** `--min-poss 0 --min-games 0`
gives the same 677 unfloored players as the arm the sweep explains, so the §7.5
table and the main evaluation are computed on identical ground and no population
caveat is needed when the two are read together.

This also corroborates the `rapm_eval_full` reconstruction above by an
independent route: the script builds precisely that invocation, with the same
floor arguments, differing only in `--alpha` and `--out`.

**α = 31,620 is the CV grid ceiling**
(`logspace(1.5, 4.5, 16)` tops out at 31,623), so the hold-out optimum sits at the
largest value CV could ever have returned — a boundary solution, carried as a Ch9
limitation. **The grid was deliberately not widened; do not re-fit to locate the
interior optimum.**

---

## VERIFIED — validation and diagnostic scripts (Unit 9)

```
python3 scripts/validate_tagging_4b.py --shots warehouse/tagged_shots_ids.parquet --outdir reports
python3 scripts/team_agg_corr.py --lo 2020 --hi 2024
python3 scripts/team_agg_corr_holdout.py --train-lo 2020 --train-hi 2024 --eval-season 2025
```

| script | establishes | output |
|---|---|---|
| `validate_tagging_4b.py` | Four-context taxonomy reproducible from pinned rules across all 610,554 attempts, agreement 1.000, rule set unique among eight candidates. Supersedes `validate_tagging.py`, which validates the retired six-context function and cannot run against the current schema. | `reports/validate_tagging_4b.json`, `action_code_census.csv`, `coordinate_integrity_by_season.csv` |
| `team_agg_corr.py` | In-window team-aggregate correlation with win pct, 2020–2024: plus-minus 0.936, RAPM 0.785, Win Score 0.689, PIR 0.666. **Falsifies the de-confounding account previously in Ch7 §7.8.** | `reports/team_agg_corr.txt` |
| `team_agg_corr_holdout.py` | Same arms frozen on 2020–2024, correlated against 2025-26: Win Score 0.712, PIR 0.574, plus-minus 0.557, RAPM 0.510. Decay orders arms by derivation from in-window team outcomes. | `reports/team_agg_corr_holdout.txt` |

**Pinned tagging rules**, recovered empirically and reported in Appendix A: corner
depth 220 cm, inclusive rim test at `r ≤ 200`, layup and dunk codes classified
at-rim directly. `relabel_four_bucket.py` implements 225 cm and a strict rim test
and **produced neither committed shot table** — it is superseded code.

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

**4. Do not re-run a committed fit to "check" it.** `rapm_baseline` is pinned
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

**6. Every fit cited in the thesis now has a recorded or determined command.**
Two entries previously listed here as gaps have been closed: `rapm_eval_full`,
whose floor argument is uniquely determined by the artifact, and the six
`sweep_a*` fits, which are generated by `sweep_alpha_holdout.py` and whose
invocations are read from its source.

**7. Check every VERIFIED entry against the filesystem.** One has already been
falsified. The tier means "string recovered from history", and nothing more.

