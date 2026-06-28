"""
play_context.py — six shot-context buckets (Chapter 5 core), outcome-independent
================================================================================
Every bucket is computable from a single shot row, for makes AND misses alike —
no "assisted" axis (assists exist only on makes, so they encode the outcome and
would corrupt a conditional RAPM). Pure functions, no I/O.

Buckets (precedence-ordered, first match wins):
    1. transition          FASTBREAK flag
    2. second_chance       SECOND_CHANCE flag
    3. at_rim              half-court layup/dunk (or 2FG inside rim radius)
    4. mid_range           half-court two beyond the rim radius
    5. corner_three        three from the corner          ┐ split by COORD;
    6. above_break_three   three above the break          ┘ PROVISIONAL until
                                                            validate_tagging.py
                                                            confirms orientation.

Coordinate system (confirmed, 2023 sample): basket at origin (0,0), units cm,
distance = hypot(COORD_X, COORD_Y); 3-pt arc ≈ 675. Thresholds below are
calibrated in the 20×5 harness — adjust there, not by guessing.
"""
from __future__ import annotations
from math import hypot

BUCKETS = ("transition", "second_chance", "at_rim", "mid_range",
           "corner_three", "above_break_three")

# ── ID_ACTION code sets (euroleague_api.shot_data source) ───────────────────────
RIM_ACTIONS   = {"LAYUPMD", "LAYUPATT", "DUNK"}
TWO_ACTIONS   = {"2FGM", "2FGA", "2FGAB"}
THREE_ACTIONS = {"3FGM", "3FGA", "3FGAB"}
# The Points feed also carries non-FGA rows (free throws FTM/FTA, etc.). Only
# field-goal attempts get a play-context bucket; everything else → None (baseline).
FG_ATTEMPTS   = RIM_ACTIONS | TWO_ACTIONS | THREE_ACTIONS

# ── coordinate calibration — CONFIRM/ADJUST in validate_tagging.py ──────────────
RIM_RADIUS          = 200    # cm; a 2FG within this of the basket counts as at_rim
SIDELINE_AXIS       = "x"    # which COORD axis runs sideline-to-sideline
CORNER_SIDELINE_MIN = 660    # |sideline coord| beyond which a three is a corner
CORNER_DEPTH_MAX    = 220    # depth coord below which a three is a corner


def _coord_dist(x, y):
    return None if x is None or y is None else hypot(x, y)


def _is_corner(x, y) -> bool:
    if x is None or y is None:
        return False
    side, depth = (abs(x), y) if SIDELINE_AXIS == "x" else (abs(y), x)
    return side >= CORNER_SIDELINE_MIN and depth <= CORNER_DEPTH_MAX


def classify(id_action: str, fastbreak: bool, second_chance: bool,
             coord_x: float | None = None, coord_y: float | None = None) -> str | None:
    """Map one field-goal attempt to a bucket, or None for non-FGA rows (free throws,
    etc.) which belong in the baseline, not the shot-context decomposition.
    coord_* optional (older seasons may lack them); without coords, threes default to
    above_break and close 2FGs to mid_range."""
    if id_action not in FG_ATTEMPTS:        # free throws and any non-shot rows
        return None
    if fastbreak:
        return "transition"
    if second_chance:
        return "second_chance"
    if id_action in THREE_ACTIONS:
        return "corner_three" if _is_corner(coord_x, coord_y) else "above_break_three"
    if id_action in RIM_ACTIONS:
        return "at_rim"
    # two-point jump shot: at_rim only if coords place it inside the rim radius
    d = _coord_dist(coord_x, coord_y)
    if d is not None and d <= RIM_RADIUS:
        return "at_rim"
    return "mid_range"