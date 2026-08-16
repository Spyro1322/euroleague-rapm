"""
At The Buzzer — landing page.

Logo, one paragraph, one button. Nothing else.

WIRING (app/streamlit_app.py), immediately after st.set_page_config(...):

    import landing

    if landing.gate():
        st.stop()          # landing is showing; render nothing else this run

    landing.home_button()  # optional: puts a "Home" control above the tabs

    # ... existing tab code from here

NOTES
  [1] The logo already carries the wordmark and the "Advanced Analytics
      Platform" line, so this page prints no heading text of its own. If the
      logo is ever swapped for a mark without type, add the heading back.

  [2] BROWSER BACK DOES NOT WORK, and cannot. Streamlit writes query params with
      history.replaceState rather than pushState, so entering the app replaces
      the current history entry instead of adding one — there is no landing
      entry left to go back to, and pressing back leaves the app. home_button()
      is the supported way back. This is a Streamlit limitation, not a bug here.

  [3] State lives in the URL (?view=app), not st.session_state. This means the
      dashboard is directly linkable — put ?view=app in the defence slides to
      skip the landing during the live demo. Trade-off: anyone arriving on that
      link never sees the landing page.

  [4] ASSET. Expects app/assets/atb_lockup.png, background stripped and margin
      trimmed by scripts/strip_logo_bg.py. If the file is missing the page still
      renders — intro and button only — rather than crashing.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

# --- content -----------------------------------------------------------------

ASSETS = Path(__file__).parent / "assets"
LOCKUP = ASSETS / "atb_lockup.png"

INTRO = (
    "Advanced analytics for Euroleague basketball. Built from possession-level "
    "data, designed to show not just what the numbers say but how much "
    "importance they can carry."
)

_ENTER_KEY = "atb_enter"
_HOME_KEY = "atb_home"
_PARAM = "view"
_VALUE = "app"


# --- styles ------------------------------------------------------------------

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600&family=Inter:wght@400&display=swap');

.atb-wrap {
    max-width: 620px;
    margin: 0 auto;
    padding: 3.5rem 1.25rem 1.5rem;
    font-family: 'Inter', system-ui, sans-serif;
}

.atb-wrap img.atb-logo {
    display: block;
    width: 320px;
    max-width: 78%;
    height: auto;
    margin: 0 auto 2rem;
}

/* Streamlit's own paragraph rules beat inherited alignment, so this is set
   on the element itself and forced. */
.atb-wrap p.atb-intro {
    text-align: center !important;
    font-size: 1.02rem;
    line-height: 1.7;
    max-width: 44ch;
    margin: 0 auto;
    color: #33415C;
}

/* --- enter button --- */
.st-key-atb_enter button {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    letter-spacing: 0.09em !important;
    text-transform: uppercase !important;
    background: #16233A !important;
    color: #F4F5F7 !important;
    border: none !important;
    border-radius: 2px !important;
    padding: 0.62rem 0 !important;
}
.st-key-atb_enter button:hover { background: #C2562B !important; }

/* --- home control, deliberately quiet --- */
.st-key-atb_home button {
    background: transparent !important;
    color: #8A8F98 !important;
    border: 1px solid #D8DBE0 !important;
    border-radius: 2px !important;
    font-size: 0.78rem !important;
    padding: 0.25rem 0 !important;
}
.st-key-atb_home button:hover {
    color: #16233A !important;
    border-color: #16233A !important;
}
</style>
"""


def _logo_html() -> str:
    """Inline as base64 — Streamlit will not serve a local file to an <img src>
    inside st.markdown unless static serving is enabled."""
    if not LOCKUP.exists():
        return ""
    b64 = base64.b64encode(LOCKUP.read_bytes()).decode()
    return f'<img class="atb-logo" src="data:image/png;base64,{b64}" alt="At The Buzzer">'


# --- public API --------------------------------------------------------------

def render() -> None:
    """Draw the landing screen. Does not gate — call gate() for that."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="atb-wrap">{_logo_html()}'
        f'<p class="atb-intro">{INTRO}</p></div>',
        unsafe_allow_html=True,
    )

    st.write("")
    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        if st.button("Open the platform", key=_ENTER_KEY, use_container_width=True):
            st.query_params[_PARAM] = _VALUE
            st.rerun()


def gate() -> bool:
    """Render the landing page if the visitor has not entered yet.

    Returns True when the landing page is showing, meaning the caller should
    st.stop() and render nothing else this run.
    """
    if st.query_params.get(_PARAM) == _VALUE:
        return False
    render()
    return True


def reset() -> None:
    """Send the visitor back to the landing screen."""
    st.query_params.clear()


def home_button(label: str = "\u2190 Home") -> None:
    """Render a quiet control that returns to the landing page.

    Call this inside the app, above the tabs. Needed because the browser back
    button cannot return here — see note [2] in the module docstring.
    """
    st.markdown(_CSS, unsafe_allow_html=True)
    _, right = st.columns([7, 1])
    with right:
        if st.button(label, key=_HOME_KEY, use_container_width=True):
            reset()
            st.rerun()