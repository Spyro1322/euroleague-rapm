"""
scripts/identifiability_pins.py

SINGLE SOURCE OF TRUTH for per-bucket identifiability verdicts.

WHY THIS MODULE EXISTS
The verdict rule ("|corr| >= 0.25 STRONG, >= 0.10 WEAK, else NONE") used to be
written out twice, independently:
  - scripts/assess_identifiability.py  -- printed the verdict and wrote
    reports/{prefix}_identifiability.json
  - scripts/export_shotctx_parquet.py  -- recomputed the SAME rule inline and
    wrote the verdict column into warehouse/shotctx_{window}.parquet

Only the second one reaches the dashboard. The deployment mirror ships parquet
only; reports/ never leaves the main repo. So the copy that governed what Tab 2
actually rendered was the one embedded in the export script, and any change made
to the assess script was cosmetic. Two copies of a rule that must agree is a
latent bug regardless of which one is "right" today.

Both scripts now import from here. There is one rule and one pin table.

WHAT IS PINNED, AND WHY
Ch5's claim is not "above_break_three scored 0.098 once." It is that the
per-bucket verdict is STABLE across three independently-fitted windows sharing
as few as 5 of 19 seasons. Measured values (full run, all three windows):

    bucket              baseline / dash / eval      verdict
    at_rim              0.481 / 0.478 / 0.472       STRONG
    mid_range           0.372 / 0.337 / 0.362       STRONG
    above_break_three   0.066 / 0.098 / 0.046       NONE   <- 0.098 vs WEAK=0.10
    corner_three        0.016 / 0.044 / 0.045       NONE

above_break_three peaks 0.002 under the WEAK cutoff, IN THE DASH WINDOW -- which
is the window the public dashboard defaults to. A re-fit (a season appended, a
different bootstrap draw, alpha drifting under a CV curve that is flat over an
order of magnitude) could cross 0.10 on noise alone while nothing about the
replication argument changes. Unpinned, that would silently turn a suppressed
spoke into a rendered one on the live dashboard, and the thesis text would no
longer describe the artifact.

THE 0.098 IS WRONG-SIGNED, WHICH IS THE STRONGER ARGUMENT
`signal` is max(|corr_off|, |corr_def|), and the abs() throws away a fact that
matters more than the magnitude. The design puts +1 on both fives while y is
points scored BY the offence, so a raw DEFENSIVE coefficient is negative-for-good
against a positive-for-good DRAPM. A real defensive effect therefore shows a
NEGATIVE corr_def. Observed:

    bucket              corr_def  baseline / dash / eval
    at_rim               -0.481 / -0.478 / -0.472   negative -- correct direction
    mid_range            -0.372 / -0.306 / -0.362   negative -- correct direction
    above_break_three    +0.042 / +0.098 / +0.033   POSITIVE in all three
    corner_three         -0.008 / +0.011 / +0.036   mixed, ~zero

above_break_three's largest correlation points the WRONG WAY in every window.
That is not a marginal real effect approaching a threshold from below; it is
what noise looks like. The pin is not papering over an inconvenient number --
it encodes a verdict the sign evidence independently supports. `sign_check()`
below surfaces this rather than leaving it implicit.

So the PUBLISHED verdict comes from PINNED_VERDICTS. The LIVE verdict is still
computed everywhere it was before, still printed, and still written to the JSON
alongside the published one -- that is the drift detector. When they disagree
the scripts warn loudly and publish the pin.

CHANGING A PIN is a methodological decision, not a re-run. Check the new number
replicates across baseline AND dash AND eval, check the SIGN is correct for the
end it comes from, then edit PINNED_VERDICTS with a reason and update the Ch5
text in the same commit.
"""

BUCKETS = ["at_rim", "mid_range", "corner_three", "above_break_three"]

# Verdict thresholds on |corr(unshrunk bucket coefficient, overall O/D RAPM)|.
STRONG, WEAK = 0.25, 0.10

# Live verdicts within this margin of a threshold are called out in the printed
# output, pinned or not, so a bucket living near a boundary is never invisible.
BORDERLINE_MARGIN = 0.02

# Expected sign of a genuine effect, by end. Offence: raw coefficient is
# positive-for-good against a positive-for-good ORAPM, so corr_off > 0.
# Defence: raw coefficient is negative-for-good against a positive-for-good
# DRAPM, so corr_def < 0. See export_shotctx_parquet.py "SIGN NORMALISATION".
EXPECTED_SIGN = {"off": +1, "def": -1}

# ---------------------------------------------------------------------------
# THE PIN TABLE. Set a bucket to None to let the live number govern it.
# ---------------------------------------------------------------------------
PINNED_VERDICTS = {
    "at_rim":            "STRONG",  # 0.472-0.481, nowhere near a boundary
    "mid_range":         "STRONG",  # 0.337-0.372, nowhere near a boundary
    "corner_three":      "NONE",    # 0.016-0.045, comfortably below WEAK
    "above_break_three": "NONE",    # 0.046-0.098; peak is 0.002 under WEAK in
                                    # the DASH window (the dashboard default).
                                    # Pinned NONE because the verdict replicates
                                    # as NONE in all three windows AND because
                                    # that peak is corr_def=+0.098, the wrong
                                    # sign for a real defensive effect in all
                                    # three. Ch5 §5.x reports it as such.
}


def classify(signal: float) -> str:
    """Live verdict from the raw signal. No pinning applied."""
    if signal != signal:  # NaN
        return "NONE"
    if signal >= STRONG:
        return "STRONG"
    if signal >= WEAK:
        return "WEAK"
    return "NONE"


def published(bucket: str, signal: float) -> tuple[str, str, bool]:
    """
    Resolve the verdict actually written to artifacts.

    Returns (published_verdict, live_verdict, drifted).
    `drifted` is True when a pin exists and disagrees with the live number --
    the caller is expected to warn, not to silently correct either way.
    """
    live = classify(signal)
    pin = PINNED_VERDICTS.get(bucket)
    if pin is None:
        return live, live, False
    return pin, live, pin != live


def borderline(signal: float) -> float | None:
    """Distance to the nearest threshold, or None if comfortably clear of both."""
    if signal != signal:
        return None
    margin = min(abs(signal - STRONG), abs(signal - WEAK))
    return margin if margin <= BORDERLINE_MARGIN else None


def sign_check(corr_off: float, corr_def: float) -> dict:
    """
    Is the correlation driving `signal` pointing the direction a real effect
    would? Returns dict(driver, value, expected_sign, correct_sign).

    A bucket whose signal is carried by a wrong-signed correlation is showing
    noise, not a weak effect -- worth stating explicitly wherever the magnitude
    alone would look borderline.
    """
    o = 0.0 if corr_off != corr_off else corr_off
    d = 0.0 if corr_def != corr_def else corr_def
    driver, value = ("off", o) if abs(o) >= abs(d) else ("def", d)
    exp = EXPECTED_SIGN[driver]
    ok = (value * exp) > 0 if value else False
    return dict(driver=driver, value=value, expected_sign=exp, correct_sign=ok)


def sign_note(corr_off: float, corr_def: float) -> str:
    """One-line human-readable form of sign_check(), or '' when the sign is fine."""
    c = sign_check(corr_off, corr_def)
    if c["correct_sign"] or not c["value"]:
        return ""
    want = "negative" if c["expected_sign"] < 0 else "positive"
    return (f"WRONG SIGN: signal carried by corr_{c['driver']}={c['value']:+.3f}, "
            f"but a real {c['driver']} effect requires {want}. Consistent with noise.")


def drift_banner(drift: dict) -> str:
    """Shared warning text so both scripts say the same thing."""
    if not drift:
        return ""
    lines = ["", "  " + "!" * 70,
             "  VERDICT DRIFT — the live recompute disagrees with the pin table in",
             "  scripts/identifiability_pins.py. Artifacts were written with the",
             "  PINNED value, so nothing downstream changed silently. This needs a",
             "  human decision, not a re-run:"]
    for bucket, d in drift.items():
        lines.append(f"    {bucket:20} live={d['live']:6}  pinned={d['pinned']:6}"
                     f"  (signal {d['signal']:.3f})")
    lines += ["  Check whether the new number replicates across baseline AND dash",
              "  AND eval, and whether the SIGN is correct for the end it comes",
              "  from, before editing the pin. If it does, update PINNED_VERDICTS",
              "  with a reason and update the Ch5 text in the same commit.",
              "  " + "!" * 70]
    return "\n".join(lines)