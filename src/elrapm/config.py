"""Project-wide constants. Single source of truth for season range + paths."""
from pathlib import Path

COMPETITION = "E"            # Euroleague
SEASON_START = 2007          # 2007-08 (proposal range start; confirm via Wk1 check)
SEASON_END = 2025            # 2025-26
EUROLEAGUE_API_MIN = "0.0.21"  # first version exposing pbp lineups; we pin 0.1.1

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LANDING = DATA / "landing"
WAREHOUSE = DATA / "warehouse"
DUCKDB_PATH = WAREHOUSE / "warehouse.duckdb"

# 7 play types (O3)
PLAY_TYPES = [
    "pnr_handler", "pnr_roller", "isolation", "spot_up",
    "post_up", "transition", "off_screen",
]
