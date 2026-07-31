"""
scripts/build_shotctx_design.py

Builds one design per (window, bucket) for shot-context RAPM (O3).

WHY PER-BUCKET AND NOT ONE STACKED MATRIX
The four buckets partition shots: every attempt is 2 or 3 by ID_ACTION, and each
side splits on one geometric threshold, so the buckets are mutually exclusive and
exhaustive by construction. A design whose rows each belong to exactly one bucket,
with bucket-specific coefficient blocks, is block-diagonal — so a single joint
ridge fit and four independent ridge fits give identical estimates. Four fits are
chosen: easier to diagnose, each bucket can carry its own alpha, and a failure in
one bucket doesn't contaminate the others.

UNITS — this is what makes the shrinkage target valid
A possession ending in an at-rim attempt is one at-rim possession. So for bucket b:
    w = number of bucket-b attempts by the offensive five in that lineup state
    y = 100 * points scored on those attempts / w
which is points per 100 possessions-of-type-b. Overall RAPM is points per 100
possessions of any type. Same denominator semantics, different subpopulation —
therefore directly comparable, therefore shrinking a bucket coefficient toward
the player's overall RAPM is meaningful. If y were points-per-attempt on some
other scale, the prior and the parameter would be in different units and the
hierarchical shrinkage would be arithmetic noise.

SCOPE CAVEAT (belongs in Ch5)
The buckets cover possessions that end in a field-goal attempt. Possessions
ending in a turnover, or in free throws only, carry no bucket and are excluded
from the context model. They remain in the overall model. Shot-context RAPM is
therefore explicitly conditional on the possession ending in a shot.

INPUTS (all confirmed present)
    warehouse/tagged_shots_ids.parquet
        Season, Gamecode, bucket, points, player_id, off_players, def_players
    warehouse/{window}_players.parquet
        col, player_id, off_offset, def_offset   (off_offset==0, def_offset==n)
    (nothing else — no pbp_poss, no stints, no bridge)

OUTPUTS, per (window, bucket)
    warehouse/shotctx_{window}_{bucket}_design.npz    y, w, groups, player_ids, meta
    warehouse/shotctx_{window}_{bucket}_design.X.npz  sparse X, cols = 2*n_players

LINEUP DISTINCTNESS IS RE-DERIVED HERE, NOT TRUSTED
Week 2 established that a persisted lineup-validity flag was uniformly true even
for stints with duplicated players, and that scipy's coo_matrix silently SUMS
duplicate (row, col) entries — turning a repeated player into a ghost 2.0
feature. Distinctness is therefore re-asserted on every row of this design with a
hard 0/1 check, regardless of what any upstream flag says.
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl
from scipy import sparse

W = Path("warehouse")

FOUR_BUCKETS = ["at_rim", "mid_range", "corner_three", "above_break_three"]
SITUATION_LABELS = {"transition", "second_chance"}

WINDOWS = {
    # ALL windows use the FOUR-bucket location-only taxonomy.
    #
    # The situation flags (FASTBREAK / SECOND_CHANCE) are populated on MADE shots
    # only -- verified on 2023: transition was 1,954 rows with zero misses,
    # second_chance 2,741 with one. Conditioning on the shot being made removes
    # the outcome variance an efficiency model exists to explain, so those two
    # buckets cannot support a rating. And because the tagger applies precedence
    # (fastbreak > second_chance > location), their presence also strips made
    # fastbreak/putback attempts out of the location buckets, biasing them
    # downward -- at_rim FG% read 54.6% with the flags active and 64.7% without.
    #
    # Ignoring the flags entirely therefore fixes two problems at once and makes
    # the taxonomy identical across all three windows. It also removes the
    # 2015-16 flag cliff from the picture: the four location buckets depend only
    # on coordinates, which are 0.97-0.99 populated in every season 2007-2025.
    # This supersedes the Week 5 "Option 1 / per-column season mask" decision.
    "baseline": dict(players="rapm_players",      lb="rapm_baseline",
                     lo=2007, hi=2025, buckets=FOUR_BUCKETS),
    "dash":     dict(players="rapm_dash_players", lb="rapm_dash",
                     lo=2021, hi=2025, buckets=FOUR_BUCKETS),
    "eval":     dict(players="rapm_eval_players", lb="rapm_eval",
                     lo=2020, hi=2024, buckets=FOUR_BUCKETS),
}


def load_player_index(players_stem: str):
    """
    Returns (pid_to_col, n_players, off_base, def_base).

    The observed layout is: `col` is the within-block index (0..n-1), `off_offset`
    is a constant block base of 0, `def_offset` a constant block base of n. So the
    offensive column for a player is off_offset + col and the defensive column is
    def_offset + col. This is asserted rather than assumed.
    """
    pm = pl.read_parquet(W / f"{players_stem}.parquet")
    n = pm.height
    off_bases = pm["off_offset"].unique().to_list()
    def_bases = pm["def_offset"].unique().to_list()
    if len(off_bases) != 1 or len(def_bases) != 1:
        raise SystemExit(
            f"{players_stem}: off_offset/def_offset are not constant block bases "
            f"(off={off_bases[:5]}, def={def_bases[:5]}). The column layout differs "
            f"from what was observed; inspect before proceeding."
        )
    off_base, def_base = int(off_bases[0]), int(def_bases[0])
    cols = pm["col"].to_numpy()
    if not np.array_equal(np.sort(cols), np.arange(n)):
        raise SystemExit(f"{players_stem}: `col` is not a 0..n-1 permutation.")
    if def_base != off_base + n:
        print(f"  NOTE: def_base ({def_base}) != off_base + n ({off_base + n}). "
              f"Using the stored values as given.")
    pids = pm["player_id"].to_list()
    if len(set(pids)) != len(pids):
        dupes = pm.group_by("player_id").agg(pl.len().alias("n")).filter(pl.col("n") > 1)
        raise SystemExit(
            f"  FATAL: {players_stem}.parquet has duplicated player_id(s):\n{dupes}\n"
            f"  dict(zip(...)) would silently keep only the last, collapsing two\n"
            f"  design columns into one. Fix the player map before continuing."
        )
    pid_to_col = dict(zip(pids, cols.tolist()))
    return pid_to_col, n, off_base, def_base


def prepare_shots(shots: pl.DataFrame, lo: int, hi: int, buckets: list):
    n0 = shots.height
    shots = shots.filter((pl.col("Season") >= lo) & (pl.col("Season") <= hi))
    print(f"  shots in {lo}-{hi}: {shots.height:,} of {n0:,}")
    if shots.is_empty():
        return shots, {}

    seasons = sorted(shots["Season"].unique().to_list())
    print(f"  seasons present: {seasons}")
    expected = list(range(lo, hi + 1))
    missing = [s for s in expected if s not in seasons]
    if missing:
        print(f"  !! WARNING: no tagged shots for seasons {missing}.")
        print(f"     This window will be estimated on {len(seasons)}/{len(expected)} "
              f"seasons. Re-run the tagger over the full range first if that matters.")

    if True:
        present = set(shots["bucket"].unique().to_list())
        if present & SITUATION_LABELS:
            raise SystemExit(
                "  FATAL: four-bucket mode requested but the tagged shots still carry\n"
                "  'transition' / 'second_chance' labels. Because the tagger applies\n"
                "  precedence, those rows have LOST their location label and it cannot be\n"
                "  recovered from the bucket column alone. Re-run the tagger with the\n"
                "  situation flags ignored to produce a location-only partition, then\n"
                "  point this script at that output via --shots.\n"
                "  Do NOT proceed by dropping those rows: it would silently delete every\n"
                "  transition and second-chance attempt from the baseline's location\n"
                "  buckets, biasing at_rim in particular."
            )

    shots = shots.filter(pl.col("bucket").is_in(buckets))
    print(f"  after bucket filter: {shots.height:,}")

    # A null `points` sums as 0, so it would silently count as a miss and depress
    # that bucket's efficiency with no signal that anything was wrong.
    n_null_pts = shots["points"].null_count()
    if n_null_pts:
        raise SystemExit(
            f"  FATAL: {n_null_pts:,} shot rows have null `points`. Summing these\n"
            f"  would treat them as misses and bias the bucket downward invisibly.\n"
            f"  Fix them upstream, or decide explicitly to drop them."
        )

    # ---- distinctness, re-derived. Week 2 lesson: do not trust an upstream flag.
    shots = shots.with_columns([
        pl.col("off_players").list.len().alias("_no"),
        pl.col("def_players").list.len().alias("_nd"),
        pl.col("off_players").list.n_unique().alias("_uo"),
        pl.col("def_players").list.n_unique().alias("_ud"),
    ])
    bad = shots.filter(
        (pl.col("_no") != 5) | (pl.col("_nd") != 5)
        | (pl.col("_uo") != 5) | (pl.col("_ud") != 5))
    if bad.height:
        print(f"  !! {bad.height:,} shot rows ({bad.height/shots.height:.4%}) do NOT have "
              f"two distinct five-man lineups. Dropped.")
        print(bad.group_by(["_no", "_nd", "_uo", "_ud"]).agg(pl.len().alias("n"))
              .sort("n", descending=True).head(8))
    shots = shots.filter(
        (pl.col("_no") == 5) & (pl.col("_nd") == 5)
        & (pl.col("_uo") == 5) & (pl.col("_ud") == 5)
    ).drop(["_no", "_nd", "_uo", "_ud"])
    print(f"  after distinctness: {shots.height:,}")

    # ---- aggregate to lineup-state x bucket
    shots = shots.with_columns([
        pl.col("off_players").list.sort().alias("off_s"),
        pl.col("def_players").list.sort().alias("def_s"),
        (pl.col("Season") * 100000 + pl.col("Gamecode")).alias("gkey"),
    ])
    agg = shots.group_by(["gkey", "Season", "Gamecode", "off_s", "def_s", "bucket"]).agg([
        pl.len().alias("attempts"),
        pl.col("points").sum().alias("points"),
    ])
    print(f"  aggregated lineup-state x bucket rows: {agg.height:,}")
    return agg, {"seasons": seasons}


def build_one(agg: pl.DataFrame, bucket: str, pid_to_col, n_players,
              off_base, def_base, min_mapped: int):
    sub = agg.filter(pl.col("bucket") == bucket)
    if sub.is_empty():
        return None

    off_lists = sub["off_s"].to_list()
    def_lists = sub["def_s"].to_list()
    attempts = sub["attempts"].to_numpy().astype(np.float64)
    points = sub["points"].to_numpy().astype(np.float64)
    gkey = sub["gkey"].to_numpy()

    rows_i, cols_i, vals = [], [], []
    keep = np.ones(len(off_lists), dtype=bool)
    unmapped_off = unmapped_def = 0

    for i, (ol, dl) in enumerate(zip(off_lists, def_lists)):
        oc = [pid_to_col[p] for p in ol if p in pid_to_col]
        dc = [pid_to_col[p] for p in dl if p in pid_to_col]
        if len(oc) < min_mapped or len(dc) < min_mapped:
            keep[i] = False
            unmapped_off += 5 - len(oc)
            unmapped_def += 5 - len(dc)
            continue
        # duplicate columns would be SUMMED by coo_matrix into a ghost 2.0
        # feature; distinctness was enforced upstream, assert it survived the
        # player-id mapping (two ids can map to one column only if the map is broken)
        if len(set(oc)) != len(oc) or len(set(dc)) != len(dc):
            raise SystemExit(
                f"  FATAL: player-id map collapses two distinct players onto one "
                f"column in bucket={bucket}, row={i}. This is the ghost-feature bug. "
                f"Fix the id map before continuing."
            )
        for c in oc:
            rows_i.append(i); cols_i.append(off_base + c); vals.append(1.0)
        for c in dc:
            rows_i.append(i); cols_i.append(def_base + c); vals.append(1.0)

    n_rows_all = len(off_lists)
    idx = np.where(keep)[0]
    if len(idx) == 0:
        return None

    n_cols = max(off_base, def_base) + n_players
    X_full = sparse.coo_matrix(
        (vals, (rows_i, cols_i)), shape=(n_rows_all, n_cols)).tocsr()
    X = X_full[idx]

    w = attempts[idx]
    y = 100.0 * points[idx] / w
    groups = gkey[idx]

    dropped = n_rows_all - len(idx)
    print(f"    [{bucket:18}] rows={len(idx):>8,}  attempts={w.sum():>10,.0f}  "
          f"y mean={y.mean():+7.2f} sd={y.std():6.2f}  dropped={dropped:,}")
    if dropped:
        print(f"      ({dropped:,} rows had fewer than {min_mapped} mapped players on a "
              f"side; sub-floor players are absent from this window's player map)")
        print(f"      unmapped player-slots on dropped rows: "
              f"{unmapped_off:,} offensive, {unmapped_def:,} defensive")

    # per-player support, for the reliability floor the dashboard applies
    support = np.asarray(X.multiply(w[:, None]).sum(axis=0)).ravel()
    return dict(X=X, y=y, w=w, groups=groups, support=support, n_dropped=dropped)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True, choices=sorted(WINDOWS))
    ap.add_argument("--shots", default=None,
                    help="override the tagged-shots parquet (use the four-bucket "
                         "re-tag output when building the baseline window)")
    ap.add_argument("--min-mapped", type=int, default=5,
                    help="minimum mapped players per side; 5 = require all five")
    ap.add_argument("--out-prefix", default=None)
    args = ap.parse_args()

    cfg = WINDOWS[args.window]
    prefix = args.out_prefix or f"shotctx_{args.window}"

    print(f"WINDOW: {args.window}  seasons {cfg['lo']}-{cfg['hi']}  "
          f"{len(cfg['buckets'])} location-only buckets")

    src_path = Path(args.shots) if args.shots else (W / "tagged_shots_ids.parquet")
    if not src_path.exists():
        raise SystemExit(f"  shots source not found: {src_path}")
    print(f"  shots source: {src_path}")
    agg, meta = prepare_shots(pl.read_parquet(src_path), cfg["lo"], cfg["hi"],
                              cfg["buckets"])

    if agg is None or agg.is_empty():
        raise SystemExit("  no usable shot rows for this window.")

    pid_to_col, n_players, off_base, def_base = load_player_index(cfg["players"])
    print(f"  player map: {n_players} players, off_base={off_base}, def_base={def_base}")

    # Any design for a bucket NOT in this window's set is stale -- from an earlier
    # taxonomy. Downstream tools discover buckets by globbing, so leaving stale
    # files on disk means they get silently fitted and rendered. Remove them.
    stale = []
    for p in sorted(W.glob(f"{prefix}_*_design.npz")):
        b = p.name[len(prefix) + 1:-len("_design.npz")]
        if b not in cfg["buckets"]:
            stale.append((b, p, W / f"{prefix}_{b}_design.X.npz"))
    if stale:
        print(f"\n  removing {len(stale)} stale bucket design(s) not in this "
              f"window's taxonomy:")
        for b, a, bx in stale:
            print(f"    {b}")
            a.unlink(missing_ok=True)
            bx.unlink(missing_ok=True)
            for extra in (W / f"{prefix}_{b}_fit.npz",):
                if extra.exists():
                    print(f"      (also removing stale fit: {extra.name})")
                    extra.unlink()

    print("\n  building per-bucket designs:")
    written = []
    for bucket in cfg["buckets"]:
        out = build_one(agg, bucket, pid_to_col, n_players, off_base, def_base,
                        args.min_mapped)
        if out is None:
            print(f"    [{bucket:18}] no rows — skipped")
            continue
        stem = f"{prefix}_{bucket}"
        sparse.save_npz(W / f"{stem}_design.X.npz", out["X"])
        np.savez(
            W / f"{stem}_design.npz",
            y=out["y"], w=out["w"], groups=out["groups"], support=out["support"],
            player_ids=np.array(list(pid_to_col.keys()), dtype=object),
            player_cols=np.array(list(pid_to_col.values())),
            n_players=n_players, off_base=off_base, def_base=def_base,
            bucket=bucket, window=args.window,
            season_lo=cfg["lo"], season_hi=cfg["hi"],
            leaderboard_stem=cfg["lb"],
        )
        written.append(stem)

    print(f"\n  wrote {len(written)} bucket design(s):")
    for s in written:
        print(f"    warehouse/{s}_design.npz  + .X.npz")
    print(f"\n  next: fit each with the window's leaderboard "
          f"({cfg['lb']}.parquet) as the shrinkage target.")


if __name__ == "__main__":
    main()