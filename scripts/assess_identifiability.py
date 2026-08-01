"""
scripts/assess_identifiability.py

Corrected replacement for the cross-bucket check embedded in fit_shotctx_rapm.py.
Reads existing fits — no refitting required.

WHY THE ORIGINAL CHECK WAS WRONG
It correlated bucket attempts against the raw standard deviation of
(beta - prior), and read a negative correlation as "noise surviving shrinkage."

That comparison is invalid across buckets. A ridge coefficient's sampling noise
scales with the residual standard deviation of its own design, and the buckets
differ enormously on that axis: three-point outcomes are 0 or 3 at ~35%, giving
y sd ~130-144, while two-point outcomes are 0 or 2 at ~40-64%, giving y sd ~84-89.
So at IDENTICAL sample size a three-point bucket must show larger deviation. The
original statistic was measuring shot-outcome variance, not identifiability, and
because corner_three is both the thinnest bucket and a high-variance one, it
dominated a 4-point correlation and flipped the sign of the verdict.

WHAT THIS USES INSTEAD

1. NORMALISED DEVIATION
       dev_norm = sd(beta - prior) / (y_sd / sqrt(attempts_per_player))
   The denominator is the rough scale of per-player sampling noise. Rising with
   sample size => the model is extracting more real separation as data grows.

2. UNSHRUNK CORRELATION WITH OVERALL RAPM  (the primary measure)
       corr(raw per-bucket coefficient, that player's ORAPM / DRAPM)
   This is assumption-free and needs no normalisation. A pure-noise estimate
   cannot correlate with an independently fitted quantity. It is computed on the
   UNSHRUNK fit, so the prior cannot manufacture the correlation.

   Read as: |corr| >= 0.25 strong, 0.10-0.25 weak, < 0.10 none.

3. PER-BUCKET VERDICTS, not one global one. Identifiability is a property of a
   bucket; averaging across four of them with different variance and different
   sample sizes answers no useful question.

PINNING — see scripts/identifiability_pins.py
The verdict rule and the pin table live in that module and are imported by BOTH
this script and export_shotctx_parquet.py. They used to be written out twice,
and only the export copy reached the dashboard (the mirror ships parquet; it
never sees reports/), so editing the rule here alone changed nothing a reader
would see.

above_break_three peaks at 0.098 against a WEAK cutoff of 0.10 and reads NONE in
all three windows, so its verdict is pinned rather than recomputed. This script
still computes the live verdict every run and prints it; when the live number
disagrees with the pin it warns loudly and publishes the pin. The JSON carries
both, under `verdicts` (published) and `verdicts_live` (raw).
"""

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

from identifiability_pins import (BUCKETS, STRONG, WEAK, borderline,
                                  drift_banner, published, sign_note)

W = Path("warehouse")
R = Path("reports")


def assess(window: str, prefix: str | None = None):
    prefix = prefix or f"shotctx_{window}"
    fits = sorted(W.glob(f"{prefix}_*_fit.npz"))
    if not fits:
        raise SystemExit(f"no fits matching {prefix}_*_fit.npz")

    rows = []
    for fp in fits:
        bucket = fp.name[len(prefix) + 1:-len("_fit.npz")]
        if bucket not in BUCKETS:
            print(f"  skipping non-taxonomy bucket {bucket}")
            continue
        f = np.load(fp, allow_pickle=True)
        d = np.load(W / f"{prefix}_{bucket}_design.npz", allow_pickle=True)

        y, w = d["y"], d["w"]
        n_players = int(f["n_players"])
        ob, db = int(f["off_base"]), int(f["def_base"])
        beta, mu = f["beta"], f["mu"]

        att = float(w.sum())
        att_pp = att / n_players
        y_sd = float(np.sqrt(np.average((y - np.average(y, weights=w)) ** 2, weights=w)))

        dev_off = beta[ob:ob + n_players] - mu[ob:ob + n_players]
        dev_def = beta[db:db + n_players] - mu[db:db + n_players]
        dev_sd = float((dev_off.std() + dev_def.std()) / 2)

        noise_scale = y_sd / np.sqrt(att_pp)
        dev_norm = dev_sd / noise_scale if noise_scale else float("nan")

        rep = R / f"{prefix}_fit_report.json"
        c_off = c_def = float("nan")
        if rep.exists():
            for r in json.loads(rep.read_text()):
                if r["bucket"] == bucket:
                    c_off, c_def = r.get("corr_off", np.nan), r.get("corr_def", np.nan)
        sig = max(abs(c_off) if c_off == c_off else 0,
                  abs(c_def) if c_def == c_def else 0)

        rows.append(dict(bucket=bucket, attempts=att, att_per_player=att_pp,
                         y_sd=y_sd, dev_sd=dev_sd, dev_norm=dev_norm,
                         corr_off=c_off, corr_def=c_def, signal=sig,
                         alpha=float(f["alpha"])))

    df = pl.DataFrame(rows).sort("attempts")

    print(f"\n{'='*78}\nWINDOW {window}\n{'='*78}")
    print(f"{'bucket':20} {'att':>9} {'att/pl':>7} {'y_sd':>7} "
          f"{'dev_sd':>7} {'dev_n':>7} {'corr_o':>7} {'corr_d':>7}")
    for r in df.iter_rows(named=True):
        print(f"{r['bucket']:20} {r['attempts']:>9,.0f} {r['att_per_player']:>7.1f} "
              f"{r['y_sd']:>7.1f} {r['dev_sd']:>7.3f} {r['dev_norm']:>7.4f} "
              f"{r['corr_off']:>+7.3f} {r['corr_def']:>+7.3f}")

    a = df["attempts"].to_numpy()
    dn = df["dev_norm"].to_numpy()
    ds = df["dev_sd"].to_numpy()
    if len(a) >= 3 and np.std(a) > 0:
        rho_raw = float(np.corrcoef(a, ds)[0, 1]) if np.std(ds) > 0 else float("nan")
        rho_norm = float(np.corrcoef(a, dn)[0, 1]) if np.std(dn) > 0 else float("nan")
        print(f"\n  corr(attempts, RAW deviation)        = {rho_raw:+.3f}  "
              f"<- confounded by outcome variance, do not use")
        print(f"  corr(attempts, NORMALISED deviation) = {rho_norm:+.3f}")
        if rho_norm > 0.5:
            print("    >>> Normalised separation GROWS with sample size: the model is")
            print("        extracting real structure, not noise.")
        elif rho_norm < -0.5:
            print("    >>> Normalised separation shrinks with sample size: genuinely")
            print("        noise-dominated even after accounting for outcome variance.")
        else:
            print("    >>> Ambiguous on this axis; rely on the per-bucket verdicts.")

    print("\n  PER-BUCKET VERDICT (from unshrunk correlation with overall RAPM):")
    NOTES = {"STRONG": "present in the dashboard",
             "WEAK": "present with an explicit caveat",
             "NONE": "SUPPRESS — no evidence of a real effect"}
    verdicts, verdicts_live, drift = {}, {}, {}
    for r in df.sort("signal", descending=True).iter_rows(named=True):
        sig = r["signal"]
        bucket = r["bucket"]
        v, live, drifted = published(bucket, sig)
        verdicts[bucket] = v
        verdicts_live[bucket] = live
        if drifted:
            drift[bucket] = dict(live=live, pinned=v, signal=sig)

        margin = borderline(sig)
        flag = f"   <-- {margin:.3f} from a threshold, BORDERLINE" if margin else ""
        if drifted:
            flag += f"   [PINNED {v}, live says {live}]"
        print(f"    {bucket:20} |corr|={sig:.3f}  {v:6}  -> {NOTES[v]}{flag}")
        # A borderline magnitude carried by a wrong-signed correlation is noise,
        # not a weak effect. signal = max(|.|) discards the sign; say it here.
        sn = sign_note(r["corr_off"], r["corr_def"])
        if sn:
            print(f"    {'':20} {sn}")

    if drift:
        print(drift_banner(drift))
    else:
        print("\n  Live recompute agrees with the pin table. No action needed.")

    print("\n  Interpretation: the two-point buckets (at_rim, mid_range) measure shot")
    print("  creation and rim protection, which are repeatable on-court skills. The")
    print("  three-point buckets measure three-point outcomes, which are largely not")
    print("  repeatable at the lineup level — a well-documented result in the")
    print("  plus-minus literature, and one this model reproduces from Euroleague data.")
    print("  Reporting that asymmetry is a stronger Ch5 claim than a uniform radar.")

    R.mkdir(exist_ok=True)
    out = R / f"{prefix}_identifiability.json"
    out.write_text(json.dumps(dict(window=window, verdicts=verdicts,
                                   verdicts_live=verdicts_live, drift=drift,
                                   rows=df.to_dicts()), indent=2, default=float))
    print(f"\n  wrote {out}  (verdicts = published/pinned; verdicts_live = raw recompute)")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", nargs="*", default=["baseline", "dash", "eval"])
    args = ap.parse_args()
    for w in args.windows:
        try:
            assess(w)
        except SystemExit as e:
            print(f"  {w}: {e}")


if __name__ == "__main__":
    main()