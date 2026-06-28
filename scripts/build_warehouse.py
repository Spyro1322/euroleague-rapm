"""
build_warehouse.py — one-time warehouse setup (supersedes export_pbp_poss.py)
============================================================================
Executes sql/schema.sql (the single source of truth) against the DuckDB database,
then exports the possession-complete view to canonical Parquet for the stint
builder. Idempotent — re-run any time, e.g. after the weekly 2025-26 refresh adds
games (the views read Parquet live, so new games appear with no reload).

    python scripts/build_warehouse.py        # run from the repo root

Produces:
    warehouse/euroleague.duckdb       views: pbp_lineups (landing), pbp_clean, pbp_poss
    warehouse/pbp_poss.parquet        input to build_stint_matrix.py
"""
from pathlib import Path
import duckdb

DB     = "warehouse/euroleague.duckdb"
SCHEMA = "sql/schema.sql"

Path("warehouse").mkdir(exist_ok=True)
con = duckdb.connect(DB)
con.execute(Path(SCHEMA).read_text())        # creates schemas, tables, and the three views

con.execute("""
COPY (SELECT * FROM warehouse.pbp_poss)
TO 'warehouse/pbp_poss.parquet' (FORMAT PARQUET)
""")

cnt   = lambda rel: con.execute(f"SELECT COUNT(*) FROM {rel}").fetchone()[0]
games = con.execute("SELECT COUNT(DISTINCT (Season, Gamecode)) FROM landing.pbp_lineups").fetchone()[0]
print(f"warehouse built → {DB}")
print(f"  landing.pbp_lineups : {cnt('landing.pbp_lineups'):,} rows · {games:,} games")
print(f"  warehouse.pbp_clean : {cnt('warehouse.pbp_clean'):,} rows  (player attribution, distinct fives)")
print(f"  warehouse.pbp_poss  : {cnt('warehouse.pbp_poss'):,} rows  (possession-complete) → warehouse/pbp_poss.parquet")
con.close()