# Fit commands — provenance record

Source of the exact invocations behind every model fit cited in the thesis.
Ch4 (baseline RAPM), Ch5 (shot-context RAPM) and Ch7 (evaluation) all reference
fits whose commands existed only in shell history; this file is that record.

**Recovered 2026-08 from `~/.bash_history` via**
`grep -h "fit_ridge_rapm\|fit_shotctx_rapm" ~/.bash_history | sort -u`

**Provenance is marked per command. Do not promote a RECONSTRUCTED command to
VERIFIED without re-deriving it from an artifact.**

---

## VERIFIED — recovered verbatim from shell history

### Committed fits (the three the thesis reports)

| stem | command | notes |
|---|---|---|
| `rapm_baseline_ci` | `python scripts/fit_ridge_rapm.py --prefix rapm --bootstrap 500 --alpha 1995.3 --out rapm_baseline_ci` | All-time 2007–2025. **α pinned, not CV-selected** — reproduces the validated Week 3 fit. 500 bootstrap resamples for the leaderboard CIs. |
| `rapm_dash` | `python scripts/fit_ridge_rapm.py --prefix rapm_dash --bootstrap 500 --out rapm_dash` | Current-form 2021–2025. **No `--alpha`** — CV selected 3162.3. Default floors. Dashboard default window. |
| `rapm_eval` | `python scripts/fit_ridge_rapm.py --prefix rapm_eval --out rapm_eval` | Hold-out-safe 2020–2024, 2025-26 fully excluded. No --alpha (CV selected 3162.3) and no --bootstrap, which defaults to 0 — this fit has NO credible intervals. Point estimates only.

### Replication fit (Ch4 validation — absent from STATUS.md before this file)

```
python scripts/fit_ridge_rapm.py --prefix rapm_olivo --min-games 50 --bootstrap 0
```

The Olivo (2024) like-for-like comparison fit. `--min-games 50` is the
distinguishing argument and does not appear in any other invocation — it matches
Olivo's inclusion criterion rather than this project's possession floors.
Ch4's replication section depends on this command; it was undocumented until now.

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

## RECONSTRUCTED — not in shell history, derived from STATUS.md carry-forward

### Shot-context fits (Ch5, O3)

`grep` for `fit_shotctx_rapm` returned **no matches**. The buffer rolled before
these were run, or they were executed in a session whose history was not
persisted. The following is reconstructed from the carry-forward note
*"Always `--force-signs +1,-1` on `fit_shotctx_rapm.py`"* and from
`SHOTCTX_ALPHA = 3162`:

```
# RECONSTRUCTED — verify against warehouse/shotctx_{window}_{bucket}_fit.npz
python scripts/fit_shotctx_rapm.py --window dash --alpha 3162 --force-signs +1,-1
python scripts/fit_shotctx_rapm.py --window baseline --alpha 3162 --force-signs +1,-1
python scripts/fit_shotctx_rapm.py --window eval --alpha 3162 --force-signs +1,-1
```

**This is an inference, not a record.** The window argument's name and form are
assumed. Before Ch5 cites any of it, confirm against the fit artifacts, which
store their own parameters:

```
python3 -c 'import numpy as np; f = np.load("warehouse/shotctx_dash_at_rim_fit.npz", allow_pickle=True); print(sorted(f.files)); print("alpha:", float(f["alpha"]))'
```

The `.npz` files are the authority. If they carry a parameter or argv record,
promote that to VERIFIED here and delete this reconstruction.

---

## Gaps and cautions

**1. `rapm_eval` has no credible intervals — RESOLVED. --bootstrap defaults to 0 (fit_ridge_rapm.py:103), and the eval command omits the flag, so that fit carries point estimates only. Ch7's reported metrics (RMSE, correlation, R², calibration slope) don't require intervals, so nothing is invalidated. But an eval-window leaderboard with error bars can't be drawn from the current artifact. If intervals are needed, α must be pinned to the value CV already selected so the point estimates reproduce exactly: python3 scripts/fit_ridge_rapm.py --prefix rapm_eval --alpha 3162.3 --bootstrap 500 --out rapm_eval. Omitting --alpha would re-run CV on a curve flat over an order of magnitude and could select a different α, changing every number Ch7 quotes.

```
grep -n "bootstrap" scripts/fit_ridge_rapm.py | head
```

**2. Ordering is not recoverable.** `HISTTIMEFORMAT` was unset, so entries carry
no timestamps, and `sort -u` discarded the file order that remained. The
sequence of scratch fits above is therefore not evidence of the order in which
they ran. Any claim of the form "X was fit before Y" needs artifact mtimes, not
this file.

**3. `--prefix` refers to a design stem, and stems are not uniform.** All-time
uses `rapm_design` + `rapm_players` while `rapm_baseline.parquet` is only the
leaderboard; `dash`/`eval` use `rapm_{w}_design` + `rapm_{w}_players`. So
`--prefix rapm` and `--prefix rapm_dash` are not parallel constructions, and
`--out` takes a stem rather than a path.

**4. Do not re-run any committed fit to "check" it.** `rapm_baseline_ci` is
pinned at α = 1995.3 precisely so it reproduces Week 3. `rapm_dash` and
`rapm_eval` let CV choose, and the CV curve is flat over an order of magnitude —
a re-run can legitimately land on a different α and silently invalidate every
number the thesis quotes, including the pinned `DASH_ALPHA = 3162.3` in the
dashboard.

**5. Preserve history going forward.** So a future gap doesn't require this
exercise again:

```
echo 'export HISTTIMEFORMAT="%F %T "' >> ~/.bashrc
echo 'export HISTSIZE=50000' >> ~/.bashrc
echo 'export HISTFILESIZE=50000' >> ~/.bashrc
```
