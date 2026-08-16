"""
Tab 4 — Methodology.

Static render. Reads no artifacts, so it cannot fail on a missing parquet in the
mirror and adds no cold-start cost. Every figure below is one that was verified
against source or artifacts (see STATUS.md, Unit 7 / Unit 9); nothing here is
recomputed at render time.
"""

import streamlit as st


def render() -> None:
    st.header("Methodology")
    st.caption(
        "Euroleague shot-context RAPM · seasons 2007-08 to 2025-26 · "
        "MSc Artificial Intelligence Applied to Sports, UCAM"
    )

    st.markdown(
        """
This dashboard renders pre-computed Parquet artifacts. No model is fitted in the
app. Everything shown was produced by the pipeline in the main repository and
mirrored here as static files.
"""
    )

    # ------------------------------------------------------------------ data
    with st.expander("1 · Data and on-court reconstruction", expanded=True):
        st.markdown(
            """
**Source.** Play-by-play, shot coordinates and boxscores from the official
Euroleague endpoints via `euroleague_api` 0.1.1. Nineteen seasons, 2007-08
through 2025-26, ingested to a Parquet warehouse with DuckDB views over it.

**Lineup reconstruction.** Ten-on-court state is reconstructed from substitution
events. Validation used a stratified sample of 95 games (five per season,
48,827 actions, seed 42):

- Every action in every season yielded two well-formed five-man lineups
  (`five_invariant` = 1.000); starters were recovered for every sampled game.
- Of 36,931 individual-action rows, **0.12%** attributed an action to a lineup
  not containing the named actor — roughly one action in 840, concentrated in
  steals recorded across a substitution beat.
- The remaining on-court-check failures are team-credited events (team rebounds,
  team turnovers) carrying no individual, and are dropped by the modelling view.

No possession-level substitution-timing correction was applied; the residual does
not justify it.
"""
        )

    # ----------------------------------------------------------------- model
    with st.expander("2 · Baseline RAPM (O2)"):
        st.markdown(
            """
**Unit of observation.** One row per team per stint — that team's *offensive*
possessions. The response `y` is **offensive points per 100 possessions**, not
point differential. Rows are weighted by possessions `w`.

**Design.** The matrix is **unsigned**: all ten non-zeros in a row are `+1`,
five attackers in the offensive block and five defenders in the defensive block.
A ±1 encoding would cancel under the column-weight recovery the pipeline relies
on. The defensive sign convention is applied *after* fitting
(`drapm = −coef[n_players:]`), so a positive DRAPM is good defence.

All-time design: **296,683 × 4,366**, 2,966,830 non-zeros — exactly ten per row,
no exceptions, 0.229% density. The 4,366 columns are 2 × 2,183 players.

**Regularisation.** Ridge over `numpy.logspace(1.5, 4.5, 16)` (31.6 … 31,623),
selected by `GroupKFold(n_splits=5)` on a composite game key
(`Season × 100000 + Gamecode`), so no game is split across folds. Both reported
α values are grid points, not hand-chosen: 1,995.3 for the all-time fit,
3,162.3 for the dashboard and evaluation windows.

**Leaderboard gate.** `MIN_POSS = 500` counting **both ends** — about 250
offensive possessions, three to four games. This is permissive by design; thin
players are shown with their intervals visible rather than filtered away.

**Overall rating.** `RAPM = ORAPM + DRAPM`. A possession-weighted alternative
diverges by less than 0.1 pts/100, so the simple sum is used.
"""
        )

    with st.expander("3 · Three-point luck adjustment"):
        st.markdown(
            """
The response is **three-point luck-adjusted**, and only three-point luck-adjusted
— two-point and free-throw points pass through as realised.

For each stint, expected points replace realised points as
`non3_pts + 3 × 3PA × lg_3P%`, where `lg_3P%` is the **league** rate for that
**season** (19 distinct values, from 0.3605 in 2007 through a trough near 0.3355
in 2010 to 0.3653 in 2023 and 0.3590 in 2025).

Two deliberate choices:

- A *league* rate, not a player rate. A player-specific rate would reintroduce
  exactly the shooting variance the adjustment is meant to remove.
- A *season-specific* rate. A pooled rate would have injected an era artefact
  into a nineteen-season panel.

The adjustment is applied inside the design build, upstream of α selection, so
the cross-validated α corresponds to the target actually fitted.
"""
        )

    # ------------------------------------------------------------ shot context
    with st.expander("4 · Shot-context tagging and conditional RAPM (O3)"):
        st.markdown(
            """
**Tagging.** 610,554 shot attempts across 19 seasons, joining to play-by-play at
99.89%. Shot-coordinate coverage is 1.000 in every season — zero unmapped rows.

Contexts are assigned from court geometry plus action codes:

| rule | threshold |
|---|---|
| at rim | radial distance ≤ 200 cm, or a layup/dunk action code |
| corner three | sideline distance ≥ 660 cm and depth ≤ 220 cm |
| above-the-break three | beyond the arc (≈ 675 cm), not corner |
| mid-range | remainder |

The full rule set, including tie-breaking order, is specified in Appendix A of
the thesis. Independent re-implementation of those rules reproduces the shipped
labels at **1.000 agreement across all 610,554 attempts** — an exhaustive check,
not a sample.

**A measurement caveat that matters for era comparisons.** The `at_rim` context
is identified by three different instruments over the study period: anomalous
coordinates in 2007, action codes from 2008 to 2014, and geometry from 2015
onward. 36.6% of all-time at-rim possessions predate 2015, and 286 of 944 rated
players have careers straddling that boundary. At-rim comparisons across the
2015 line are comparisons across instruments.

**Fitting.** Per-context designs are fitted with cross-validated α (the modal
value is 3,162, but three of twelve fits differ, so a fixed α would not reproduce
them). Identifiability is assessed per context against pinned thresholds; only
contexts passing that test are reported as separable, and the tab labels the
verdict for each.
"""
        )

    # -------------------------------------------------------------- intervals
    with st.expander("5 · Bootstrap intervals — read them correctly"):
        st.warning(
            "Interval width is **not** a reliability measure on this leaderboard.",
            icon="⚠️",
        )
        st.markdown(
            """
Intervals are bootstrap resamples at seed 42. Counter-intuitively, **width rises
with possessions**: `corr(width, log poss) = +0.484`, with quartile median widths
of 3.495 / 4.391 / 4.904 / 4.625 against median possessions of
788 / 1,774 / 4,044 / 11,009. Median width is 4.466.

The mechanism is the penalty, not the data. A thin player is shrunk hard, so his
coefficient barely moves across resamples — the narrowness records the **strength
of the penalty**, not the precision of the estimate. Heavy-possession players
escape the penalty and are free to move.

Two consequences carried into the thesis:

- A narrow interval does not mean a well-estimated player.
- Sorting by the lower bound would make the thin-player problem *worse*, because
  the same shrinkage that narrows a thin interval also props up its lower bound.
"""
        )

    # ------------------------------------------------------------- evaluation
    with st.expander("6 · Held-out evaluation, and the null"):
        st.markdown(
            """
Train 2020–2024, hold out 2025-26, frozen scaling, 402 games. The naive arm is a
fitted home-advantage constant of +3.77 points, which sits inside the published
Euroleague range and serves as a harness sanity check.

| arm | RMSE | vs naive | corr | R² | slope |
|---|---|---|---|---|---|
| win_score | 11.604 | +5.08% | 0.322 | 0.099 | 3.19 |
| pir | 11.910 | +2.58% | 0.268 | 0.051 | 2.70 |
| rapm | 12.009 | +1.77% | 0.226 | 0.035 | 1.57 |
| shotctx | 12.064 | +1.32% | 0.216 | 0.026 | 1.43 |
| naive | 12.225 | — | — | 0 | — |

**RAPM does not beat the box-score baselines at predicting game margin, and the
thesis reports this as a result rather than tuning around it.** An α sweep shows
calibration and accuracy are in direct opposition along the regularisation path:
the best-calibrated fit (slope 1.04, α = 100) is the *worst* predictor
(−6.20% vs naive), while the best RMSE sits at the CV grid ceiling with a
calibration slope of 3.88 and player spread collapsed to 0.23 pts/100. Optimal α
closes 42% of the gap to Win Score; the remainder is not attributable to α.

At stint level the null is structural rather than a model failure: with roughly
four possessions per stint, noise dominates to the point that attainable R² is
capped near 0.01 regardless of how good the ratings are.

What RAPM *does* do is de-confound team context. Aggregated to team level against
win percentage over 2020–2024, RAPM correlates at 0.785 against 0.666–0.689 for
the box-score arms — the ordering reverses relative to margin prediction.
"""
        )

    # ---------------------------------------------------------- reproducibility
    with st.expander("7 · Reproducibility and refresh"):
        st.markdown(
            """
Two repositories: a private main repo holding the full ingestion, design-build,
fitting and evaluation pipeline, and a public mirror holding the app plus the
pre-computed Parquet artifacts it renders. The mirror is watched by Streamlit
Community Cloud.

Fit commands are recorded in `docs/fit_commands.md` and tiered by provenance —
RECONSTRUCTED, VERIFIED (the command string was recovered from shell history) and
VERIFIED BY ENTAILMENT (the artifact's contents entail the command that produced
it). The distinction is deliberate: a recovered string certifies what was typed,
not that it ran or produced the cited file.

The refresh workflow is a **reproduction path**, not a live cron. Artifacts here
are regenerated deliberately and re-mirrored, so what you see is a fixed,
citable state rather than a moving target.
"""
        )

    st.divider()
    st.markdown(
        """
**Repository:** <https://github.com/Spyro1322/euroleague-rapm-dashboard>
"""
    )


if __name__ == "__main__":
    st.set_page_config(page_title="Methodology", layout="wide")
    render()
