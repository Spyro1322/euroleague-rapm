"""
scripts/diagnose_wk6_round2.py

Resolves the four remaining unknowns before the stacked design matrix can be built:

  A. Does tagged_shots_ids cover 2007-2025, or only one season?
  B. Can shots reach stints via pbp_poss on (Season, Gamecode, NUM_ANOT) -> stint_id?
     (If not, is the lineup-set fallback viable and how ambiguous is it?)
  C. What is the per-window player -> base-column mapping, and does it reconcile
     with the base X column count?
  D. What filter reproduces each design's row order from stints_ids, exactly?
  E. Are the six buckets a strict partition, and do transition/second_chance
     override the location buckets? (Confirms or refutes the precedence finding.)

Read-only. Writes nothing. Paste the whole output back.
"""

from pathlib import Path

import numpy as np
import polars as pl
from scipy import sparse

W = Path("warehouse")

# (design_stem, players_stem, leaderboard_stem, season_lo, season_hi)
WINDOWS = [
    ("rapm_design",      "rapm_players",      "rapm_baseline", 2007, 2025),
    ("rapm_dash_design", "rapm_dash_players", "rapm_dash",     2021, 2025),
    ("rapm_eval_design", "rapm_eval_players", "rapm_eval",     2020, 2024),
]

BUCKETS = ["transition", "second_chance", "at_rim", "mid_range",
           "corner_three", "above_break_three"]


def hr(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


# ----------------------------------------------------------------- A
def section_a():
    hr("A. TAGGED SHOT COVERAGE  (is the tagger run full-range or one season?)")
    p = W / "tagged_shots_ids.parquet"
    if not p.exists():
        print("  MISSING tagged_shots_ids.parquet")
        return
    df = pl.read_parquet(p)
    by_season = df.group_by("Season").agg(
        pl.len().alias("shots"),
        pl.col("Gamecode").n_unique().alias("games"),
    ).sort("Season")
    print(f"  total rows: {df.height:,}")
    print(f"  distinct seasons: {df['Season'].n_unique()}")
    print(by_season)
    seasons = sorted(df["Season"].unique().to_list())
    print(f"\n  season list: {seasons}")
    if len(seasons) < 19:
        print(f"\n  >>> VERDICT: tagger has run on {len(seasons)} season(s), NOT 19.")
        print("      The full-range TAGGING step is outstanding. Locate the raw shot")
        print("      shards and re-run the tagger before the stacked design.")
    else:
        print("\n  >>> VERDICT: full-range tagging present.")

    # where did the raw ingest actually land?
    print("\n  Searching for raw shot shards outside warehouse/ ...")
    hits = []
    for pat in ["shots", "raw", "data"]:
        for d in Path(".").rglob(f"*{pat}*"):
            if d.is_dir():
                n = len(list(d.rglob("*.parquet")))
                if n:
                    hits.append((str(d), n))
    for d, n in sorted(set(hits))[:20]:
        print(f"    {d}: {n} parquet file(s)")
    if not hits:
        print("    (none found under cwd — check the ingest output path)")


# ----------------------------------------------------------------- B
def section_b():
    hr("B. SHOTS -> STINTS BRIDGE")
    shots = pl.read_parquet(W / "tagged_shots_ids.parquet")
    stints = pl.read_parquet(W / "stints_ids.parquet")

    pp = W / "pbp_poss.parquet"
    if pp.exists():
        poss = pl.read_parquet(pp)
        print("  pbp_poss.parquet schema:")
        for k, v in poss.schema.items():
            print(f"    {k:28s} {v}")
        cols = set(poss.columns)
        need = {"Season", "Gamecode", "NUM_ANOT"}
        has_stint = [c for c in poss.columns if "stint" in c.lower()]
        print(f"\n    has (Season, Gamecode, NUM_ANOT)? {need.issubset(cols)}")
        print(f"    stint-like columns: {has_stint}")

        if need.issubset(cols) and has_stint:
            sc = has_stint[0]
            br = poss.select(["Season", "Gamecode", "NUM_ANOT", sc]).unique(
                subset=["Season", "Gamecode", "NUM_ANOT"])
            j = shots.select(["Season", "Gamecode", "NUM_ANOT"]).join(
                br, on=["Season", "Gamecode", "NUM_ANOT"], how="left")
            matched = j.filter(pl.col(sc).is_not_null()).height
            print(f"\n    >>> BRIDGE VIABLE: {matched:,}/{shots.height:,} shots "
                  f"({100*matched/shots.height:.2f}%) resolve to {sc}")
            if matched < shots.height:
                miss = j.filter(pl.col(sc).is_null())
                print(f"        unmatched by season:")
                print(miss.group_by("Season").agg(pl.len()).sort("Season"))
        else:
            print("\n    >>> pbp_poss does NOT carry both the event index and a stint id.")
    else:
        print("  pbp_poss.parquet MISSING")

    # lineup-set fallback: how unique is a 10-man state within a game?
    print("\n  Lineup-set fallback viability (are 10-man states unique per game?):")
    st = stints.with_columns([
        pl.col("home_players").list.sort().list.join("|").alias("h"),
        pl.col("away_players").list.sort().list.join("|").alias("a"),
    ])
    dup = st.group_by(["Season", "Gamecode", "h", "a"]).agg(
        pl.len().alias("n")).filter(pl.col("n") > 1)
    print(f"    stints: {st.height:,} | 10-man states recurring within a game: {dup.height:,}")
    if dup.height:
        print(f"    max recurrences of one state in a game: {dup['n'].max()}")
        print("    >>> lineup-set join would be MANY-TO-MANY on those. pbp bridge preferred.")
    else:
        print("    >>> every 10-man state unique within its game; lineup join is safe.")


# ----------------------------------------------------------------- C
def section_c():
    hr("C. PER-WINDOW PLAYER -> BASE COLUMN MAPPING")
    for design_stem, players_stem, lb_stem, lo, hi in WINDOWS:
        pmap = W / f"{players_stem}.parquet"
        dnpz = W / f"{design_stem}.npz"
        dx = W / f"{design_stem}.X.npz"
        print(f"\n  [{design_stem}] players={players_stem}")
        if not pmap.exists():
            print(f"    MISSING {pmap}")
            continue
        pm = pl.read_parquet(pmap)
        print(f"    rows={pm.height}  cols={pm.columns}")
        print(pm.head(3))
        if not dx.exists():
            print(f"    MISSING {dx}")
            continue
        X = sparse.load_npz(dx)
        print(f"    X shape = {X.shape}")
        print(f"    n_players*2 = {pm.height*2}  -> matches X cols? {pm.height*2 == X.shape[1]}")
        for c in ("off_offset", "def_offset", "col"):
            if c in pm.columns:
                s = pm[c]
                print(f"    {c}: min={s.min()} max={s.max()} "
                      f"contiguous={sorted(s.to_list()) == list(range(s.min(), s.min()+pm.height))}")
        # do the offsets actually index into X?
        if {"off_offset", "def_offset"}.issubset(pm.columns):
            mx = max(pm["off_offset"].max(), pm["def_offset"].max())
            print(f"    max offset={mx} vs X cols={X.shape[1]} -> in range? {mx < X.shape[1]}")


# ----------------------------------------------------------------- D
def section_d():
    hr("D. DESIGN ROW ORDER — which stints_ids filter reproduces `groups` exactly?")
    stints = pl.read_parquet(W / "stints_ids.parquet")
    stints = stints.with_columns(
        (pl.col("Season") * 100000 + pl.col("Gamecode")).alias("gkey"))

    # candidate row-selection filters, tried in order
    def f_base(df, lo, hi):
        return df.filter((pl.col("Season") >= lo) & (pl.col("Season") <= hi))

    cands = {
        "season only": lambda df, lo, hi: f_base(df, lo, hi),
        "season + poss>0": lambda df, lo, hi: f_base(df, lo, hi).filter(pl.col("poss") > 0),
        "season + lineup_ok": lambda df, lo, hi: f_base(df, lo, hi).filter(pl.col("lineup_ok")),
        "season + lineup_ok + poss>0": lambda df, lo, hi:
            f_base(df, lo, hi).filter(pl.col("lineup_ok") & (pl.col("poss") > 0)),
        "season + distinct5": lambda df, lo, hi: f_base(df, lo, hi).filter(
            (pl.col("home_players").list.n_unique() == 5)
            & (pl.col("away_players").list.n_unique() == 5)),
        "season + distinct5 + poss>0": lambda df, lo, hi: f_base(df, lo, hi).filter(
            (pl.col("home_players").list.n_unique() == 5)
            & (pl.col("away_players").list.n_unique() == 5)
            & (pl.col("poss") > 0)),
    }

    for design_stem, _, _, lo, hi in WINDOWS:
        dnpz = W / f"{design_stem}.npz"
        if not dnpz.exists():
            print(f"\n  [{design_stem}] MISSING")
            continue
        d = np.load(dnpz, allow_pickle=True)
        groups = d["groups"]
        n = len(groups)
        print(f"\n  [{design_stem}] design rows = {n:,}   seasons {lo}-{hi}")
        gs = np.unique(groups // 100000)
        print(f"    design season span: {gs.min()} -> {gs.max()}  (n={len(gs)})")

        for label, fn in cands.items():
            sub = fn(stints, lo, hi)
            m = sub.height
            for mult, mlabel in ((1, "1 row/stint"), (2, "2 rows/stint")):
                if m * mult != n:
                    continue
                g_stint = sub["gkey"].to_numpy()
                cand = g_stint if mult == 1 else np.repeat(g_stint, 2)
                exact = bool(np.array_equal(cand, groups))
                cand_i = np.concatenate([g_stint, g_stint]) if mult == 2 else cand
                exact_i = bool(np.array_equal(cand_i, groups))
                print(f"    {label:32s} x{mult} ({mlabel}): count MATCH  "
                      f"order-exact(interleaved)={exact}  order-exact(stacked)={exact_i}")
            if m * 1 != n and m * 2 != n:
                print(f"    {label:32s} count {m:,} (x2={m*2:,}) -> no")

        # multiset check: ignores order, catches "right rows, wrong order"
        best = None
        for label, fn in cands.items():
            sub = fn(stints, lo, hi)
            for mult in (1, 2):
                if sub.height * mult != n:
                    continue
                a = np.sort(np.repeat(sub["gkey"].to_numpy(), mult))
                if np.array_equal(a, np.sort(groups)):
                    best = f"{label} x{mult}"
        print(f"    >>> multiset match: {best if best else 'NONE FOUND'}")


# ----------------------------------------------------------------- E
def section_e():
    hr("E. BUCKET PRECEDENCE — partition, and do flags override location?")
    df = pl.read_parquet(W / "tagged_shots_ids.parquet")
    print(f"  rows={df.height:,}   sum of bucket counts must equal rows if partition")
    vc = df.group_by("bucket").agg(pl.len().alias("n")).sort("n", descending=True)
    print(vc)
    print(f"  sum = {vc['n'].sum():,}  ==  rows? {vc['n'].sum() == df.height}")

    def norm(c):
        return (pl.col(c).cast(pl.Utf8).fill_null("0").str.strip_chars()
                .replace({"": "0", "-": "0", "False": "0", "false": "0",
                          "True": "1", "true": "1"}))

    d2 = df.with_columns([norm("FASTBREAK").alias("fb"), norm("SECOND_CHANCE").alias("sc")])
    print("\n  raw flag values present:")
    print(d2.group_by("fb").agg(pl.len()).sort("fb"))
    print(d2.group_by("sc").agg(pl.len()).sort("sc"))

    print("\n  CROSS-TAB bucket x (fastbreak, second_chance):")
    ct = d2.group_by(["bucket", "fb", "sc"]).agg(pl.len().alias("n")).sort(
        ["bucket", "fb", "sc"])
    with pl.Config(tbl_rows=80):
        print(ct)

    print("\n  >>> READ THIS: if rows exist where bucket is a LOCATION bucket")
    print("      (at_rim/mid_range/corner_three/above_break_three) AND fb='1' or sc='1',")
    print("      then flags do NOT override location and the two axes are independent.")
    print("      If location buckets are ~always fb=0,sc=0, then precedence IS applied")
    print("      and the location buckets change meaning across the 2015-16 flag cliff.")

    loc = ["at_rim", "mid_range", "corner_three", "above_break_three"]
    leak = d2.filter(pl.col("bucket").is_in(loc) & ((pl.col("fb") == "1") | (pl.col("sc") == "1")))
    print(f"\n  location-bucket rows carrying a positive flag: {leak.height:,}")
    if leak.height == 0:
        print("      >>> PRECEDENCE CONFIRMED. Use the 4-bucket baseline / 6-bucket")
        print("          dash+eval split. Do NOT rely on the per-column mask alone.")
    else:
        print("      >>> Axes are independent; the per-column mask is sufficient after all.")


if __name__ == "__main__":
    for fn in (section_a, section_b, section_c, section_d, section_e):
        try:
            fn()
        except Exception as e:
            print(f"\n  !! {fn.__name__} failed: {type(e).__name__}: {e}")
    print("\n" + "=" * 72)
    print("Paste this whole output back.")
    print("=" * 72)
