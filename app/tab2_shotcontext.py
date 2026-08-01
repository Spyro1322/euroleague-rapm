"""
app/tab2_shotcontext.py

Tab 2 — shot-context RAPM radar. Four location buckets.

Call `render(warehouse_dir)` from the Tab 2 container in streamlit_app.py.

DEPENDENCY: introduces plotly, which was deliberately removed from the mirror
repo's requirements.txt in Week 5 as unused. Add the pin, then rerun the Week 5
clean-venv smoke test against the two-tab app before deploying. Check the current
version against PyPI rather than trusting a number written here, and confirm a
wheel exists for whatever CPython Community Cloud resolves to -- the same trap
that produced the slow pandas source build.

Reads {warehouse}/shotctx_{window}.parquet from export_shotctx_parquet.py.
Rendering only, no fitting.

WHAT THIS TAB HONESTLY SHOWS
Week 6 tested whether per-bucket deviations survive shrinkage as real effects.
Normalised for the differing outcome variance across contexts, corr(bucket
attempts, deviation) = +0.925: deviations grow with exposure, as a real effect
should. An earlier unnormalised figure of -0.994 measured shot variance rather
than identifiability and reported the verdict backwards; it is withdrawn. The
binding limit is instead per-context identifiability -- two of four contexts show
no repeatable individual effect. A radar renders noise as confident geometry, and
the thinnest bucket produces the most dramatic spoke. So this tab:
  - gates every value on on-court support, and shows what was withheld
  - draws the player's overall RAPM as a reference ring, because deviation from
    the ring -- not the absolute value -- is the claim being made
  - shows that deviation explicitly beside the radar rather than leaving the
    reader to eyeball distances
  - states the identifiability limit in the open while the data still shows it
Presenting per-bucket rankings without these would overstate what the model knows.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

BUCKETS = ["at_rim", "mid_range", "corner_three", "above_break_three"]
BUCKET_LABELS = {
    "at_rim": "At rim",
    "mid_range": "Mid-range",
    "corner_three": "Corner 3",
    "above_break_three": "Above-break 3",
}
MIN_OVERALL_POSS = 3000
WINDOW_LABELS = {
    "baseline": "All-time (2007\u20132025)",
    "dash": "Recent form (5-season)",
}
PALETTE = {("off", 1): "#1f77b4", ("def", 1): "#d62728",
           ("off", 2): "#2ca02c", ("def", 2): "#ff7f0e"}


@st.cache_data(show_spinner=False)
def load_shotctx(warehouse_dir: str, window: str) -> pd.DataFrame:
    df = pd.read_parquet(f"{warehouse_dir}/shotctx_{window}.parquet")
    df["bucket"] = pd.Categorical(df["bucket"], categories=BUCKETS, ordered=True)
    return df


# @st.cache_data(show_spinner=False)
# def identifiability(df: pd.DataFrame) -> float:
#     """corr(median support, deviation sd) across buckets. Strongly negative = noise."""
#     g = (df[df["end"] == "off"].groupby("bucket", observed=True)
#          .agg(sup=("support", "median"), dev=("deviation", "std")).dropna())
#     if len(g) < 3 or g["sup"].std() == 0 or g["dev"].std() == 0:
#         return float("nan")
#     return float(np.corrcoef(g["sup"], g["dev"])[0, 1])


def _frame(df: pd.DataFrame, player_id: str, end: str) -> pd.DataFrame:
    sub = df[(df["player_id"] == player_id) & (df["end"] == end)].copy()
    sub = sub.set_index("bucket").reindex(BUCKETS).reset_index()
    # Two independent gates, kept separate because they mean different things:
    #   identified — is this bucket estimable AT ALL? (bucket-level)
    #   reliable   — does THIS player have enough on-court exposure? (player-level)
    # A bucket that fails the first must never render, whatever the second says.
    sub["identified"] = (sub["verdict"].ne("NONE")
                         if "verdict" in sub.columns else True)
    sub["enough"] = sub["reliable"].fillna(False)
    sub["shown"] = sub["enough"] & sub["identified"]

    # Three states, three visual treatments:
    #   shown            -> the fitted value, solid marker
    #   not identified   -> PINNED TO THE PRIOR, hollow grey marker. For a bucket
    #                       with no measurable signal the model's best estimate
    #                       genuinely IS the player's overall rating, so drawing
    #                       it on the ring is the honest representation and makes
    #                       the flatness of those axes the visible finding.
    #                       Plotting the fitted noise instead would invent an
    #                       effect; leaving a gap would hide the asymmetry.
    #   identified but thin -> GAP. A different claim: not "no effect exists" but
    #                       "not enough exposure for this player to say".
    sub["plot_value"] = sub["value"].where(sub["shown"])
    pin = (~sub["identified"]) & sub["prior"].notna()
    sub.loc[pin, "plot_value"] = sub.loc[pin, "prior"]
    sub["pinned"] = pin
    return sub


def _radar(frames, rings, title, unidentified=()):
    fig = go.Figure()
    thetas = [BUCKET_LABELS[b] + (" \u2020" if b in unidentified else "")
              for b in BUCKETS]

    for label, (val, color) in rings.items():
        fig.add_trace(go.Scatterpolar(
            r=[val] * len(thetas) + [val], theta=thetas + [thetas[0]],
            name=f"{label} overall", mode="lines",
            line=dict(color=color, width=1, dash="dot"),
            hovertemplate=f"{label} overall: {val:+.2f}<extra></extra>"))

    for f, label, color, dash in frames:
        vals = f["plot_value"].tolist()
        pinned = f["pinned"].tolist()
        m_color = ["#9A9A9A" if p else color for p in pinned]
        m_symbol = ["circle-open" if p else "circle" for p in pinned]
        m_size = [7 if p else 9 for p in pinned]
        status = ["not identified — shown at overall rating" if p
                  else "fitted" for p in pinned]
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=thetas + [thetas[0]],
            name=label, mode="lines+markers",
            line=dict(color=color, dash=dash, width=2),
            marker=dict(size=m_size + [m_size[0]],
                        color=m_color + [m_color[0]],
                        symbol=m_symbol + [m_symbol[0]],
                        line=dict(color=color, width=1.5)),
            customdata=status + [status[0]],
            connectgaps=False,  # a gap must LOOK like a gap, not read as zero
            hovertemplate="%{theta}: %{r:+.2f} pts/100<br>%{customdata}"
                          "<extra>" + label + "</extra>"))

    allv = [v for f, _, _, _ in frames for v in f["plot_value"].dropna()]
    allv += [v for v, _ in rings.values()]
    lim = max(2.0, max(abs(v) for v in allv) * 1.2) if allv else 2.0

    if unidentified:
        fig.add_annotation(
            text="\u2020 no measurable player effect in this context — "
                 "drawn on the overall-rating ring",
            xref="paper", yref="paper", x=0.5, y=-0.08, showarrow=False,
            font=dict(size=11, color="#7A7A7A"))

    fig.update_layout(
        title=title, height=520, showlegend=True,
        margin=dict(l=60, r=60, t=60, b=70),
        polar=dict(radialaxis=dict(visible=True, range=[-lim, lim],
                                   tickformat="+.1f"),
                   angularaxis=dict(direction="clockwise")))
    return fig


def _deviation_chart(frames):
    """Deviation from the prior is the actual claim; show it, don't imply it."""
    fig = go.Figure()
    labels = [BUCKET_LABELS[b] for b in BUCKETS]
    for f, label, color, _ in frames:
        dev = (f["value"] - f["prior"]).where(f["shown"])
        # A bucket pinned to the prior has, by definition, zero deviation. Drawing
        # its fitted-minus-prior here would contradict the radar, which shows it on
        # the ring, and would present noise as an effect.
        dev = dev.mask(f["pinned"], 0.0)
        cols = ["#C8C8C8" if p else color for p in f["pinned"]]
        fig.add_trace(go.Bar(x=labels, y=dev.tolist(), name=label,
                             marker_color=cols,
                             hovertemplate="%{x}: %{y:+.2f} vs overall"
                                           "<extra>" + label + "</extra>"))
    fig.add_hline(y=0, line=dict(color="#888", width=1))
    fig.update_layout(
        height=280, barmode="group", showlegend=False,
        margin=dict(l=40, r=20, t=40, b=40),
        title="Deviation from the player's overall rating (pts/100)",
        yaxis_title="above / below own average")
    return fig


def render(warehouse_dir: str):
    st.subheader("Shot-context RAPM")

    col_a, col_b = st.columns(2)
    with col_a:
        window = st.selectbox("Rating window", list(WINDOW_LABELS),
                              format_func=lambda k: WINDOW_LABELS[k],
                              key="sc_window")
    try:
        df = load_shotctx(warehouse_dir, window)
    except FileNotFoundError:
        st.warning(f"No shot-context artifact for {WINDOW_LABELS[window]} yet "
                   f"(expected `shotctx_{window}.parquet`).")
        return

    if "verdict" in df.columns:
        vb = (df.groupby("bucket", observed=True)
                .agg(verdict=("verdict", "first"), signal=("signal", "first")))
        strong = [BUCKET_LABELS[b] for b in BUCKETS
                  if b in vb.index and vb.loc[b, "verdict"] != "NONE"]
        none_ = [BUCKET_LABELS[b] for b in BUCKETS
                 if b in vb.index and vb.loc[b, "verdict"] == "NONE"]
        if none_:
            st.info(
                f"**{' and '.join(none_)} are not shown.** Player impact is "
                f"measurably identifiable for {' and '.join(strong)}, but not for "
                f"{' or '.join(none_)}: those estimates show no correlation with a "
                f"player's overall rating, i.e. no evidence of a repeatable "
                f"individual effect. Three-point outcomes being largely "
                f"non-repeatable at lineup level is a known result, and this model "
                f"reproduces it. The axes remain on the chart so the asymmetry is "
                f"visible rather than hidden.")

    st.caption(
        "Each spoke is the player's estimated impact on possessions ending in that "
        "kind of shot, in points per 100 such possessions. Positive is good on both "
        "ends. The dotted ring is the player's overall RAPM \u2014 the value each "
        "estimate is shrunk toward, and therefore the null hypothesis. "
        "**Distance from the ring is the claim**; a radar sitting on its ring means "
        "no context-specific effect was found.")

    named = df[df["name"].notna() & (df["poss"] >= MIN_OVERALL_POSS)]
    elig = named[["player_id", "name", "poss"]].drop_duplicates().sort_values("name")
    if elig.empty:
        st.warning(f"No players clear the {MIN_OVERALL_POSS:,}-possession floor.")
        return
    labels = {r.player_id: f"{r.name}  ({int(r.poss):,} poss)"
              for r in elig.itertuples()}

    with col_b:
        compare = st.toggle("Compare two players", key="sc_compare")

    p1 = st.selectbox("Player", list(labels), format_func=lambda k: labels[k],
                      key="sc_p1")
    p2 = None
    if compare:
        others = [k for k in labels if k != p1]
        p2 = st.selectbox("Compare with", others,
                          format_func=lambda k: labels[k], key="sc_p2")

    end_choice = st.radio("End", ["off", "def", "both"],
                          format_func={"off": "Offense", "def": "Defense",
                                       "both": "Both"}.get,
                          horizontal=True, key="sc_end")
    ends = ["off", "def"] if end_choice == "both" else [end_choice]

    frames, rings = [], {}
    for slot, pid in ((1, p1), (2, p2)):
        if pid is None:
            continue
        pname = elig.loc[elig["player_id"] == pid, "name"].iloc[0]
        for end in ends:
            f = _frame(df, pid, end)
            if f["plot_value"].notna().sum() == 0:
                st.info(f"{pname}: no bucket clears the support floor on "
                        f"{'offense' if end == 'off' else 'defense'}.")
                continue
            tag = "O" if end == "off" else "D"
            frames.append((f, f"{pname} ({tag})", PALETTE[(end, slot)],
                           "solid" if slot == 1 else "dash"))
            pr = f["prior"].dropna()
            if not pr.empty:
                rings[f"{pname} {tag}"] = (float(pr.iloc[0]), PALETTE[(end, slot)])

    if not frames:
        st.warning("Nothing to plot for this selection.")
        return

    unident = {b for b in BUCKETS
               if not bool(frames[0][0].set_index("bucket").loc[b, "identified"])}
    st.plotly_chart(_radar(frames, rings, "Shot-context impact (pts / 100)",
                           unidentified=unident),
                    width='stretch')
    st.plotly_chart(_deviation_chart(frames), width='stretch')

    withheld = []
    for f, label, _, _ in frames:
        for row in f[~f["shown"] & f["identified"]].itertuples():
            sup = 0 if pd.isna(row.support) else int(row.support)
            why = "on-court exposure below the reliability floor"
            withheld.append({"Series": label,
                             "Bucket": BUCKET_LABELS[row.bucket],
                             "On-court attempts": sup,
                             "Withheld because": why})
    if withheld:
        with st.expander(f"{len(withheld)} bucket(s) withheld — why", expanded=False):
            st.dataframe(pd.DataFrame(withheld), hide_index=True,
                         width='stretch')
            st.caption("A missing spoke means the estimate was suppressed, not that "
                       "the value was zero.")

    with st.expander("Method and how to read this", expanded=False):
        lm = (df.groupby("bucket", observed=True)["league_mean"].first()
              .reindex(BUCKETS))
        st.markdown(
            "- **Units** are points per 100 possessions of that shot type, the same "
            "scale as the overall leaderboard. A possession ending in an at-rim "
            "attempt is one at-rim possession.\n"
            "- **Defence is sign-corrected** so higher always means the player "
            "helped.\n"
            "- **The ring is the prior, not zero.** Each bucket estimate is "
            "hierarchically shrunk toward the player's overall rating, so the ring "
            "is what the model assumes absent evidence.\n"
            "- **Thin buckets shrink hardest.** A spoke near the ring is weak "
            "evidence of no effect, not strong evidence of it. Check the on-court "
            "attempt counts before reading a null.\n"
            "- **Scope:** buckets cover possessions ending in a field-goal attempt. "
            "Turnovers and free-throw-only possessions are excluded here and remain "
            "in the overall rating.\n"
            "- **Situation contexts (fastbreak, second-chance) are deliberately "
            "absent.** The Euroleague feed populates those flags on made shots only, "
            "so they cannot support an efficiency estimate.")
        st.write("League average by bucket (pts/100):")
        st.dataframe(
            pd.DataFrame({"Bucket": [BUCKET_LABELS[b] for b in BUCKETS],
                          "League mean": lm.round(1).values}),
            hide_index=True, width='stretch')