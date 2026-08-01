"""
app/tab3_archetypes.py

Tab 3 — shot-context archetypes (O4).

Call `render(warehouse_dir)` from the Tab 3 container in streamlit_app.py.

Reads {warehouse}/shotctx_archetypes_dash.parquet, written by decide_tab3_format.py.
Rendering only, no fitting.

WHY ARCHETYPES AND NOT A SIMILARITY RANKING
O4 was originally a lineup-pair synergy model, rescoped to a similarity finder, and
the finder was then tested before shipping. It failed:

  Neighbour-set agreement between the dash (2021-2025) and eval (2020-2024) fitting
  windows was Jaccard@10 = 0.147, and flat across K (0.092 at K=1, 0.089 at K=3,
  0.105 at K=5). Those two windows share FOUR OF FIVE SEASONS, so ~85% turnover in
  the neighbour list on ~80% shared data is a failure, not a marginal pass. Ranking
  individual players by similarity is not defensible on this data.

  Cluster membership over the same players survived: adjusted Rand index +0.405 at
  k=5, and stable across every k from 3 to 8 (+0.321 to +0.405). ARI is
  chance-corrected, so 0 is a random partition.

That contrast is itself the finding, and this tab states it rather than hiding it:
in a densely populated continuous space, WHICH player is nearest flips under small
perturbations of the fit, but WHICH REGION a player occupies does not. So the tab
shows regions, and deliberately offers no "10 most similar players" list.

The space is four-dimensional (at_rim and mid_range, offence and defence). The two
three-point contexts are excluded because Ch5 found them non-identifiable, and
including them collapses the reliably-placed population from 362 players to 118
while reordering neighbourhoods almost completely (Jaccard 0.102).
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ARTIFACT = "shotctx_archetypes_dash.parquet"

BUCKET_SHORT = {"at_rim": "rim", "mid_range": "mid"}
END_SHORT = {"off": "offence", "def": "defence"}

# Qualitative palette; index is the archetype id, which is arbitrary and can change
# if the clustering is re-run. Nothing downstream may depend on a specific id.
PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
           "#8c564b", "#e377c2", "#17becf"]


@st.cache_data(show_spinner=False)
def load_archetypes(warehouse_dir: str) -> pd.DataFrame:
    return pd.read_parquet(f"{warehouse_dir}/{ARTIFACT}")


def z_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.startswith("z__"))


def axis_label(zcol: str) -> str:
    bucket, end = zcol[3:].rsplit("__", 1)
    return f"{BUCKET_SHORT.get(bucket, bucket)} {END_SHORT.get(end, end)}"


def describe(profile: pd.Series) -> str:
    """Name an archetype from its two strongest axes.

    Derived, never hardcoded: cluster ids are arbitrary and shift whenever the
    clustering is re-run, so a fixed id->name table would silently mislabel.
    """
    top = profile.reindex(profile.abs().sort_values(ascending=False).index)[:2]
    parts = []
    for col, v in top.items():
        parts.append(("high " if v > 0 else "low ") + axis_label(col))
    return " / ".join(parts)


@st.cache_data(show_spinner=False)
def project(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """PCA to two dimensions for display only. The clustering was fitted in the
    full four-dimensional space, so two points close on this plot are not
    necessarily close in the space -- the caption says so."""
    zc = z_columns(df)
    Z = df[zc].to_numpy()
    Zc = Z - Z.mean(axis=0)
    U, S, Vt = np.linalg.svd(Zc, full_matrices=False)
    coords = Zc @ Vt[:2].T
    var = (S ** 2 / np.sum(S ** 2))[:2]
    return coords, var, zc


def _scatter(df, coords, var, highlight_pid=None):
    fig = go.Figure()
    for a in sorted(df["archetype"].unique()):
        m = df["archetype"] == a
        fig.add_trace(go.Scatter(
            x=coords[m.values, 0], y=coords[m.values, 1],
            mode="markers", name=f"A{a}",
            marker=dict(size=8, color=PALETTE[a % len(PALETTE)], opacity=0.75,
                        line=dict(width=0.5, color="#FFFFFF")),
            text=df.loc[m, "label"],
            hovertemplate="%{text}<extra>A" + str(a) + "</extra>"))

    if highlight_pid is not None:
        m = (df["player_id"] == highlight_pid).values
        if m.any():
            fig.add_trace(go.Scatter(
                x=coords[m, 0], y=coords[m, 1], mode="markers",
                name="selected", showlegend=False,
                marker=dict(size=18, color="rgba(0,0,0,0)",
                            line=dict(width=2.5, color="#111111")),
                hoverinfo="skip"))

    fig.update_layout(
        height=520, margin=dict(l=40, r=20, t=50, b=40),
        title="Shot-context space (2-D projection of 4 dimensions)",
        xaxis_title=f"PC1 — {var[0]*100:.0f}% of variance",
        yaxis_title=f"PC2 — {var[1]*100:.0f}% of variance",
        legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def _profile_chart(profiles: pd.DataFrame, zc: list[str], focus: int | None):
    fig = go.Figure()
    labels = [axis_label(c) for c in zc]
    for a in profiles.index:
        vis = True if focus is None else (a == focus)
        fig.add_trace(go.Bar(
            x=labels, y=profiles.loc[a, zc].tolist(), name=f"A{a}",
            marker_color=PALETTE[a % len(PALETTE)],
            opacity=1.0 if vis else 0.25,
            hovertemplate="%{x}: %{y:+.2f} sd<extra>A" + str(a) + "</extra>"))
    fig.add_hline(y=0, line=dict(color="#888", width=1))
    fig.update_layout(
        height=300, barmode="group",
        margin=dict(l=40, r=20, t=50, b=40),
        title="Archetype profiles (mean standardised deviation per axis)",
        yaxis_title="sd from league mean",
        legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def render(warehouse_dir: str):
    st.subheader("Shot-context archetypes")

    try:
        df = load_archetypes(warehouse_dir)
    except FileNotFoundError:
        st.warning(f"No archetype artifact yet (expected `{ARTIFACT}`). "
                   f"Run `decide_tab3_format.py`.")
        return

    zc = z_columns(df)
    k = df["archetype"].nunique()

    st.caption(
        "Players are grouped by the **shape** of their shot-context impact — where "
        "they add or lose value relative to their own overall rating — not by how "
        "good they are. Each axis is standardised, so 0 is the league average "
        "deviation and units are standard deviations. Groups cut across playing "
        "positions by design: this is a profile of contextual impact, not a "
        "position classifier.")

    st.info(
        f"**What this tab does and does not claim.** Membership of a group is "
        f"stable: refitting on a different five-season window reproduces the same "
        f"partition at an adjusted Rand index of +0.429 (0 would be random), and "
        f"that holds for every group count from 3 to 7, so k={k} is a presentational "
        f"choice rather than a tuned one. **Individual similarity is not stable** — "
        f"the ten nearest players to a given player agree only 13% between windows "
        f"that share four of five seasons. That is why this tab shows regions and "
        f"deliberately offers no 'most similar players' ranking.")

    profiles = (df.groupby("archetype")[zc].mean())
    sizes = df.groupby("archetype").size()

    mode = st.radio("View", ["By archetype", "By player"], horizontal=True,
                    key="ar_mode")

    focus = None
    highlight = None

    if mode == "By archetype":
        opts = list(profiles.index)
        focus = st.selectbox(
            "Archetype", opts,
            format_func=lambda a: f"A{a} — {describe(profiles.loc[a])}  "
                                  f"({sizes[a]} players)",
            key="ar_focus")
    else:
        labels = df.sort_values("label")[["player_id", "label", "archetype"]]
        pid = st.selectbox(
            "Player", labels["player_id"].tolist(),
            format_func=lambda p: labels.loc[labels["player_id"] == p,
                                             "label"].iloc[0],
            key="ar_player")
        highlight = pid
        focus = int(df.loc[df["player_id"] == pid, "archetype"].iloc[0])
        st.markdown(f"**{df.loc[df['player_id'] == pid, 'label'].iloc[0]}** is in "
                    f"**A{focus}** — {describe(profiles.loc[focus])}.")

    coords, var, _ = project(df)
    st.plotly_chart(_scatter(df, coords, var, highlight), width="stretch")
    st.caption(
        "Projection is for display only. The grouping was computed in the full "
        "four-dimensional space, so two players that look close here may not be "
        "close in the space — which is also why no distance ranking is offered.")

    st.plotly_chart(_profile_chart(profiles, zc, focus), width="stretch")

    if focus is not None:
        members = (df[df["archetype"] == focus]
                   .sort_values("tot_support", ascending=False)
                   [["label", "tot_support", "min_support", "prior"]]
                   .rename(columns={"label": "Player",
                                    "tot_support": "On-court attempts (total)",
                                    "min_support": "Thinnest context",
                                    "prior": "Overall RAPM"}))
        with st.expander(f"A{focus} — all {len(members)} players", expanded=False):
            st.dataframe(members, hide_index=True, width="stretch",
                         column_config={
                             "Overall RAPM": st.column_config.NumberColumn(
                                 format="%+.2f"),
                             "On-court attempts (total)":
                                 st.column_config.NumberColumn(format="%d"),
                             "Thinnest context":
                                 st.column_config.NumberColumn(format="%d")})
            st.caption(
                "Ordered by on-court exposure, **not** by similarity to any other "
                "player — a within-group ranking would reintroduce exactly the "
                "unstable claim this tab avoids.")

    with st.expander("Method, coverage and limitations", expanded=False):
        st.markdown(
            f"- **Space:** four axes — at-rim and mid-range, offence and defence. "
            f"Each is the player's per-context rating minus their overall rating, "
            f"then standardised across players.\n"
            f"- **Deviation, not raw value.** Per-context ratings correlate at 0.707 "
            f"with each other, but that is entirely the shared prior they are shrunk "
            f"toward (predicted null 0.709). Grouping on raw values would rank "
            f"players by overall quality wearing a context label. Distance in this "
            f"space correlates with the gap in overall rating at just +0.06.\n"
            f"- **Why the three-point contexts are absent.** Ch5 found no "
            f"identifiable individual effect for corner or above-break threes. "
            f"Adding them cuts the reliably-placed population from {len(df)} to 119 "
            f"and reorders groupings almost completely.\n"
            f"- **Coverage: {len(df)} players.** A player is placed only if they "
            f"clear the reliability floor in all four contexts. Others are absent "
            f"from this tab — absence means insufficient exposure, not an average "
            f"profile.\n"
            f"- **Group ids are arbitrary** and change if the clustering is re-run; "
            f"the profiles, not the numbers, carry the meaning.\n"
            f"- **The four axes are near-equally important** (20–31% of variance "
            f"each), so no single dimension dominates. The leading axis contrasts "
            f"at-rim with mid-range offence — the rim-tilt contrast reported in "
            f"Ch5, recovered here without supervision.")
