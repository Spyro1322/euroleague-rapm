"""
scripts/inspect_wk6_assumptions.py

Read-only. Answers the two flags left open in the Week 6 scripts by inspecting what
the warehouse ACTUALLY contains, then prints a verdict for each.

Run from repo root:  python3 scripts/inspect_wk6_assumptions.py

FLAG 1 — where does the fitted overall RAPM live, and under what column names?
         (fit_shotcontext_rapm.py currently guesses {stem}_players.npz with
          player_ids / o_rapm / d_rapm)
FLAG 2 — can tagged_shots be joined to stints, and do per-bucket possession
         weights already exist?
         (build_shotcontext_design.py currently assumes {bucket}_poss_off/_def)

Touches nothing. Prints only.
"""

import sys
from pathlib import Path

import numpy as np

try:
    import polars as pl
except ImportError:
    sys.exit("polars not importable — run inside the project venv/container.")

try:
    from scipy import sparse
except ImportError:
    sparse = None

WAREHOUSE = Path(sys.argv[1] if len(sys.argv) > 1 else "warehouse")

BUCKETS = ["transition", "second_chance", "at_rim", "mid_range",
           "corner_three", "above_break_three"]

# column-name candidates, case-insensitive
OFF_RAPM_HINTS = ["orapm", "o_rapm", "off_rapm", "offensive_rapm", "rapm_off"]
DEF_RAPM_HINTS = ["drapm", "d_rapm", "def_rapm", "defensive_rapm", "rapm_def"]
PID_HINTS = ["player_id", "playerid", "pid", "player_key"]
CONTEXT_HINTS = ["shot_context", "context", "bucket", "shot_bucket",
                 "play_context", "play_type", "shot_zone"]
STINT_HINTS = ["stint_id", "stint", "stint_idx", "stint_key", "possession_id"]


def hr(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def find_col(cols, hints):
    lower = {c.lower(): c for c in cols}
    for h in hints:
        if h in lower:
            return lower[h]
    # substring fallback
    for c in cols:
        for h in hints:
            if h in c.lower():
                return c
    return None


def peek_parquet(path):
    try:
        lf = pl.scan_parquet(path)
        schema = lf.collect_schema()
        n = lf.select(pl.len()).collect().item()
        return dict(schema), n
    except Exception as e:
        print(f"  !! could not read {path.name}: {e}")
        return None, None


def peek_npz(path):
    try:
        d = np.load(path, allow_pickle=True)
        out = {}
        for k in d.files:
            try:
                a = d[k]
                out[k] = (getattr(a, "shape", None), getattr(a, "dtype", None))
            except Exception:
                out[k] = ("<unreadable>", None)
        return out
    except Exception as e:
        print(f"  !! could not read {path.name}: {e}")
        return None


# ---------------------------------------------------------------- inventory
hr("0. WAREHOUSE INVENTORY")
if not WAREHOUSE.is_dir():
    sys.exit(f"No warehouse dir at {WAREHOUSE.resolve()} — pass the path as argv[1], "
             f"or cd to the repo root first.")

entries = sorted(WAREHOUSE.iterdir())
for p in entries:
    kind = "dir " if p.is_dir() else "file"
    size = "" if p.is_dir() else f"  {p.stat().st_size / 1e6:8.2f} MB"
    print(f"  {kind}  {p.name}{size}")


def resolve(stem):
    """Find stem as .parquet file, bare dir of parquet parts, or .npz."""
    for cand in (WAREHOUSE / f"{stem}.parquet", WAREHOUSE / f"{stem}.npz"):
        if cand.exists():
            return cand, cand.suffix
    d = WAREHOUSE / stem
    if d.is_dir():
        parts = sorted(d.glob("**/*.parquet"))
        if parts:
            return d, ".parquet-dir"
    return None, None


# ------------------------------------------------------- FLAG 1: overall RAPM
hr("1. FLAG 1 — fitted overall RAPM artifact + column names")

rapm_candidates = ["rapm_baseline", "rapm_dash", "rapm_eval", "rapm_players",
                   "rapm_olivo_baseline"]
flag1 = {}

for stem in rapm_candidates:
    path, kind = resolve(stem)
    if path is None:
        print(f"\n  [{stem}] NOT FOUND")
        continue
    print(f"\n  [{stem}] -> {path.name}  ({kind})")
    if kind == ".npz":
        arrays = peek_npz(path)
        if arrays:
            for k, (shape, dt) in arrays.items():
                print(f"      {k:24s} shape={shape} dtype={dt}")
            flag1[stem] = {"path": str(path), "kind": "npz", "keys": list(arrays)}
    else:
        target = path if kind == ".parquet" else path / "**/*.parquet"
        schema, n = peek_parquet(target if kind == ".parquet" else path)
        if schema is None:
            continue
        print(f"      rows={n}")
        for c, dt in schema.items():
            print(f"      {c:24s} {dt}")
        cols = list(schema)
        off_c = find_col(cols, OFF_RAPM_HINTS)
        def_c = find_col(cols, DEF_RAPM_HINTS)
        pid_c = find_col(cols, PID_HINTS)
        print(f"      --> player_id col : {pid_c}")
        print(f"      --> off RAPM col  : {off_c}")
        print(f"      --> def RAPM col  : {def_c}")
        flag1[stem] = {"path": str(path), "kind": "parquet", "rows": n,
                       "pid": pid_c, "off": off_c, "def": def_c}
        if pid_c and off_c and def_c:
            try:
                head = pl.read_parquet(path).select(
                    [c for c in [pid_c, off_c, def_c] if c]
                ).head(3)
                print(f"      sample:\n{head}")
            except Exception:
                pass

# ------------------------------------------- FLAG 1b: player index / X alignment
hr("1b. FLAG 1b — base design shape vs player table (column alignment)")

design_stems = [s for s in ["rapm_baseline", "rapm_eval", "rapm_dash"]
                if (WAREHOUSE / f"{s}_design.npz").exists()]
if not design_stems:
    print("  No *_design.npz found. Looked for rapm_{baseline,eval,dash}_design.npz.")
    print("  Actual npz files present:")
    for p in WAREHOUSE.glob("*.npz"):
        print(f"    {p.name}")

for stem in design_stems:
    print(f"\n  [{stem}_design.npz]")
    arrays = peek_npz(WAREHOUSE / f"{stem}_design.npz")
    if arrays:
        for k, (shape, dt) in arrays.items():
            print(f"      {k:24s} shape={shape} dtype={dt}")
        has_pids = any("player" in k.lower() for k in arrays)
        print(f"      --> carries a player_ids array? {'YES' if has_pids else 'NO'}")

    xp = WAREHOUSE / f"{stem}_design.X.npz"
    if xp.exists() and sparse is not None:
        try:
            X = sparse.load_npz(xp)
            print(f"      X shape = {X.shape}  (rows={X.shape[0]}, cols={X.shape[1]})")
            for pstem in ["rapm_players", stem]:
                ppath, pkind = resolve(pstem)
                if ppath and pkind in (".parquet", ".parquet-dir"):
                    _, n = peek_parquet(ppath)
                    if n:
                        print(f"      vs {pstem}: rows={n}  "
                              f"X.cols/rows = {X.shape[1] / n:.4f}  "
                              f"(2.0 => [off|def] blocks, 1.0 => single block)")
        except Exception as e:
            print(f"      !! could not load X: {e}")

# ---------------------------------------------------- FLAG 2: shots <-> stints
hr("2. FLAG 2 — tagged shots, stints, and whether the join/weights exist")

for stem in ["tagged_shots_ids", "tagged_shots", "stints_ids", "stints"]:
    path, kind = resolve(stem)
    if path is None:
        print(f"\n  [{stem}] NOT FOUND")
        continue
    print(f"\n  [{stem}] -> {path.name} ({kind})")
    schema, n = peek_parquet(path)
    if schema is None:
        continue
    print(f"      rows={n}")
    for c, dt in schema.items():
        print(f"      {c:24s} {dt}")
    cols = list(schema)
    ctx_c = find_col(cols, CONTEXT_HINTS)
    stint_c = find_col(cols, STINT_HINTS)
    pid_c = find_col(cols, PID_HINTS)
    season_c = find_col(cols, ["season"])
    game_c = find_col(cols, ["gamecode", "game_code", "game_id"])
    print(f"      --> context col   : {ctx_c}")
    print(f"      --> stint key col : {stint_c}")
    print(f"      --> player_id col : {pid_c}")
    print(f"      --> season col    : {season_c}")
    print(f"      --> gamecode col  : {game_c}")

    present_weight_cols = [c for c in cols
                           if any(b in c.lower() for b in BUCKETS)]
    print(f"      --> per-bucket weight-ish cols already present: "
          f"{present_weight_cols if present_weight_cols else 'NONE'}")

    if ctx_c:
        try:
            vc = (pl.read_parquet(path)
                    .group_by(ctx_c).len().sort("len", descending=True))
            print(f"      distinct {ctx_c} values:\n{vc}")
        except Exception as e:
            print(f"      !! value_counts failed: {e}")

# join feasibility
hr("2b. FLAG 2b — join feasibility test (shots -> stints)")
sp_path, sp_kind = resolve("tagged_shots_ids")
st_path, st_kind = resolve("stints_ids")
if sp_path and st_path:
    try:
        shots = pl.read_parquet(sp_path)
        stints = pl.read_parquet(st_path)
        s_stint = find_col(shots.columns, STINT_HINTS)
        t_stint = find_col(stints.columns, STINT_HINTS)
        print(f"  shots stint key : {s_stint}")
        print(f"  stints stint key: {t_stint}")
        if s_stint and t_stint:
            n_match = (shots.select(pl.col(s_stint).unique())
                            .join(stints.select(pl.col(t_stint).unique().alias(s_stint)),
                                  on=s_stint, how="inner").height)
            n_shot_keys = shots[s_stint].n_unique()
            print(f"  DIRECT STINT JOIN AVAILABLE: {n_match}/{n_shot_keys} "
                  f"shot stint-keys match a stint row "
                  f"({100 * n_match / max(n_shot_keys, 1):.1f}%)")
        else:
            print("  NO shared stint key -> shots must be mapped to stints by "
                  "(season, gamecode, clock/period interval). That is real work, "
                  "not a column rename.")
            for nm, df in (("shots", shots), ("stints", stints)):
                clockish = [c for c in df.columns
                            if any(h in c.lower() for h in
                                   ["clock", "time", "minute", "second", "period",
                                    "quarter", "marker", "playnumber", "play_number",
                                    "action_id", "numberofplay"])]
                print(f"    {nm} time/order cols: {clockish}")
    except Exception as e:
        print(f"  !! join test failed: {e}")
else:
    print("  Missing tagged_shots_ids or stints_ids — cannot test.")

hr("3. VERDICTS")
print("""
FLAG 1 (fit_shotcontext_rapm.py :: load_baseline_rapm)
  Read section 1. If the overall RAPM lives in a .parquet (expected, since Parquet
  is the canonical store) rather than {stem}_players.npz, the loader MUST be
  rewritten to read parquet, and the three column names it uses must be replaced
  with the actual ones printed as "player_id col / off RAPM col / def RAPM col".

FLAG 1b (build_shotcontext_design.py :: load_player_index)
  Read section 1b. If "carries a player_ids array? NO", the design npz does not
  store the player order and load_player_index() will raise. The player->column
  mapping must come from whichever table gives X.cols/rows == 2.0 (off|def blocks),
  and the context blocks must be built in THAT SAME row order.

FLAG 2 (build_shotcontext_design.py :: build_context_blocks)
  Read sections 2 and 2b.
  - "per-bucket weight-ish cols: NONE" => the {bucket}_poss_off/_def columns do
    not exist yet and must be produced by a new aggregation step (shots grouped
    to stint x bucket, then pivoted wide). Expected outcome.
  - "DIRECT STINT JOIN AVAILABLE: ~100%" => that aggregation is cheap.
  - "NO shared stint key" => a shots->stint interval mapper is needed first, and
    that is the true first task of Week 6, ahead of the stacked matrix.
""")
print("Paste this whole output back and the two scripts get patched to match exactly.\n")
