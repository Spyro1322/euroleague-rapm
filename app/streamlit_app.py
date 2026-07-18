"""
streamlit_app.py -- Euroleague RAPM dashboard (O5).

Renders pre-computed Parquet ONLY -- no training in the Space (proposal constraint).
Week 4 ships Tab 1 (RAPM leaderboard with bootstrap CIs). Tabs 2-5 are stubs that
later weeks fill in. Point DATA_DIR at the warehouse locally; the Space bundles the
same parquet artifacts (Wk5).

Inputs (written by fit_ridge_rapm.py --bootstrap):
    {DATA_DIR}/rapm_dash.parquet       current-form (2021-25), default view
    {DATA_DIR}/rapm_baseline.parquet   all-time (2007-26), optional toggle
Columns: name, poss, ORAPM, DRAPM, RAPM, RAPM_lo, RAPM_hi
         (+ first_season/last_season if present).
"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

# Defaults to a warehouse/ beside this file; override for other layouts / HF Spaces.
DATA_DIR = Path(os.environ.get("RAPM_WAREHOUSE", Path(__file__).parent / "warehouse"))
DISPLAY_MIN_POSS = 3000  # display filter only; the model fits at min-poss 500

st.set_page_config(page_title="Euroleague RAPM", layout="wide")


@st.cache_data(show_spinner=False)
def load(name: str) -> pd.DataFrame:
    p = DATA_DIR / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def ci_str(lo, hi):
    if pd.isna(lo) or pd.isna(hi):
        return ""
    return f"[{lo:+.2f}, {hi:+.2f}]"


def leaderboard_tab():
    src = st.radio(
        "Rating window",
        options=["Current form (2021-26)", "All-time (2007-26)"],
        horizontal=True,
        help="Current form = 5-season rolling window, refreshed weekly. "
             "All-time = full career pool (historical leaderboard, not current).",
    )
    fname = "rapm_dash.parquet" if src.startswith("Current") else "rapm_baseline.parquet"
    df = load(fname)
    if df.empty:
        st.warning(f"`{DATA_DIR/fname}` not found. Run "
                   f"`fit_ridge_rapm.py --prefix ... --bootstrap 500 --out ...` first.")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    min_poss = c1.number_input("Min possessions (display)", min_value=0,
                               value=DISPLAY_MIN_POSS, step=250)
    end = c2.selectbox("Rank by", ["RAPM", "ORAPM", "DRAPM"])
    query = c3.text_input("Search player", "")

    view = df.copy()
    if "poss" in view.columns:
        view = view[view["poss"] >= min_poss]
    if query and "name" in view.columns:
        view = view[view["name"].str.contains(query, case=False, na=False)]
    view = view.sort_values(end, ascending=False).reset_index(drop=True)
    view.insert(0, "#", view.index + 1)

    # Career span across the WHOLE dataset, not the rating window -- label it as such
    # so the current-form view doesn't read as if it fit all those seasons.
    if {"first_season", "last_season"}.issubset(view.columns):
        view["Career span"] = (view["first_season"].astype("Int64").astype(str)
                               + "-" + view["last_season"].astype("Int64").astype(str))

    for m in ("RAPM", "ORAPM", "DRAPM"):
        lo, hi = f"{m}_lo", f"{m}_hi"
        if lo in view.columns and hi in view.columns:
            view[f"{m} 95% CI"] = [ci_str(a, b) for a, b in zip(view[lo], view[hi])]

    show = ["#", "name", "Career span", "poss", "ORAPM", "ORAPM 95% CI",
            "DRAPM", "DRAPM 95% CI", "RAPM", "RAPM 95% CI"]
    show = [c for c in show if c in view.columns]

    st.dataframe(
        view[show],
        hide_index=True,
        width="stretch",
        height=640,
        column_config={
            "name": st.column_config.TextColumn("Player", width="medium"),
            "poss": st.column_config.NumberColumn("Poss", format="%d"),
            "ORAPM": st.column_config.NumberColumn(format="%+.2f"),
            "DRAPM": st.column_config.NumberColumn("DRAPM (+ = good D)", format="%+.2f"),
            "RAPM": st.column_config.NumberColumn(format="%+.2f"),
        },
    )
    st.caption(
        f"{len(view)} players shown (min {min_poss:,} possessions). "
        "ORAPM = offensive coef; DRAPM sign-flipped so positive = better defence; "
        "RAPM = ORAPM + DRAPM. 95% CI from a game-level cluster bootstrap. "
        "Luck-adjusted target (3-pt makes replaced by expected)."
    )


def main():
    st.title("Euroleague RAPM")
    st.caption("Regularized Adjusted Plus-Minus, 2007-08 to 2025-26. "
               "Pre-computed artifacts; no live training.")
    t1, t2, t3, t4, t5 = st.tabs(
        ["Leaderboard", "Play-type radar", "Synergy", "Similarity", "Methodology"])
    with t1:
        leaderboard_tab()
    for tab, label, wk in ((t2, "Play-type radar", 6), (t3, "Synergy", 8),
                           (t4, "Similarity finder", 9), (t5, "Methodology", 9)):
        with tab:
            st.info(f"{label} - coming in Week {wk}.")


if __name__ == "__main__":
    main()