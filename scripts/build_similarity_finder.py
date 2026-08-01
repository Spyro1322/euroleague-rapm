#!/usr/bin/env python3
"""
build_similarity_finder.py — O4 deliverable (v2).

Nearest-neighbour finder in shot-context space, running on the per-bucket fits
already on disk (warehouse/shotctx_{window}.parquet). No new fits.

WHY v2 REPLACED v1 — record this in Ch6, it is a real methodological point.
v1 ranked neighbours by cosine and returned Tavares ~ Dorsey at +0.96 and a
+1.00 match for Sloukas. The cause is shrinkage, not a bug: a low-support player
is pulled almost entirely onto their prior, so their deviation vector has
near-zero length and an essentially arbitrary direction. Cosine normalises
length away, so those noise vectors align with anyone. Observed p95 cosine of
+0.809 in four dimensions is what random directions look like, not signal.

  - PRIMARY metric is Euclidean distance on z-scored deviations. Distance keeps
    magnitude, so a shrunk-to-zero player sits near the origin and is far from a
    large-deviation player like Tavares. This is the metric Tab 3 should show.
  - Cosine is retained per pair as a secondary column: "same shape, ignoring how
    far from average", which is a legitimate but different question.
  - Players are gated on the export's own `reliable` flag in every included
    cell, so near-origin noise vectors never enter the space at all.

DESIGN DECISIONS CARRIED OVER FROM v1 (all still hold):

  1. Similarity uses `deviation`, not `value`. corr(value) = 0.707 between
     contexts against a predicted null of 0.709 from the shared prior alone, so
     `value` similarity would rank players by overall RAPM in disguise.
     corr(deviation) = -0.026: genuinely independent axes.

  2. Each (bucket, end) column is z-scored across the filtered population before
     any distance is taken. Raw deviation sd differs by outcome variance
     (above_break 0.75-0.77 vs corner 0.39-0.43), and the LEAST identifiable
     bucket has the LARGEST spread. Unnormalised, three-point noise would
     dominate the metric. Do not remove the z-scoring.

  3. --buckets defaults to `identified` (at_rim, mid_range). Ch5 split-window
     stability: at_rim 0.481/0.478/0.472, mid_range 0.372/0.337/0.362, against
     above_break 0.066/0.098/0.046 and corner 0.016/0.044/0.045. Run --compare
     to produce the agreement figure between the two bucket sets.

Outputs (warehouse/ and reports/):
  similarity_{window}_{bucketset}.parquet        long-form top-k neighbours
  shotctx_vectors_{window}_{bucketset}.parquet   wide per-player vectors (raw + z)
  reports/similarity_{window}_{bucketset}.txt    run report

Usage:
  python3 scripts/build_similarity_finder.py --window dash
  python3 scripts/build_similarity_finder.py --window dash --compare
  python3 scripts/build_similarity_finder.py --window dash --no-require-reliable
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

BUCKETS_ALL = ["at_rim", "mid_range", "above_break_three", "corner_three"]
BUCKETS_IDENTIFIED = ["at_rim", "mid_range"]
ENDS = ["off", "def"]


def load_names(warehouse: Path, log: list[str]) -> pl.DataFrame:
    """player_id_map is (name, season) keyed with up to 19 rows per player.
    Take the most recent season's spelling as the display name."""
    path = warehouse / "player_id_map.parquet"
    if not path.exists():
        log.append(f"WARNING: {path} absent — labels fall back to player_id")
        return pl.DataFrame({"player_id": [], "name": []},
                            schema={"player_id": pl.String, "name": pl.String})
    m = pl.read_parquet(path)
    names = (
        m.sort("season", descending=True)
        .group_by("player_id")
        .agg(pl.col("name").first().alias("name"))
    )
    log.append(f"name map: {m.height} rows -> {names.height} distinct player_id")
    return names


def load_long(window: str, warehouse: Path) -> pl.DataFrame:
    path = warehouse / f"shotctx_{window}.parquet"
    if not path.exists():
        sys.exit(f"missing: {path}")
    df = pl.read_parquet(path)
    required = {"player_id", "bucket", "end", "value", "prior", "deviation",
                "support", "reliable"}
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"{path} missing columns: {sorted(missing)}")
    return df


def build_vectors(df, names, buckets, require_reliable, min_support, log):
    """Long -> filtered wide -> z-scored matrix."""
    # Two ID schemes coexist: P\d{6} and a legacy 4-char P[A-Z]{3} (PBCN = BELINELLI,
    # PJDR = TEODOSIC, PCCD = DATOME). An earlier regex gate assumed the numeric form
    # and silently dropped 27 real players from the dash window. The map is the
    # authority on personhood, not the string format.
    n0 = df["player_id"].n_unique()
    df = df.join(names.select("player_id"), on="player_id", how="inner")
    n1 = df["player_id"].n_unique()
    if n0 != n1:
        log.append(f"dropped {n0 - n1} id(s) absent from player_id_map")

    df = df.filter(pl.col("bucket").is_in(buckets))

    # Gate on the export's own reliability criterion, applied to every included
    # cell. A player unreliable in any one context has no defensible position on
    # that axis, so they are excluded rather than placed at a fabricated origin.
    if require_reliable:
        ok = (
            df.group_by("player_id")
            .agg(pl.col("reliable").all().alias("all_reliable"))
            .filter(pl.col("all_reliable"))
            .select("player_id")
        )
        n_pre = df["player_id"].n_unique()
        df = df.join(ok, on="player_id", how="inner")
        log.append(f"reliability gate: {n_pre} -> {df['player_id'].n_unique()} players "
                   f"(reliable in all {len(buckets) * 2} cells)")

    if min_support > 0:
        ok = (
            df.group_by("player_id")
            .agg(pl.col("support").min().alias("min_sup"))
            .filter(pl.col("min_sup") >= min_support)
            .select("player_id")
        )
        n_pre = df["player_id"].n_unique()
        df = df.join(ok, on="player_id", how="inner")
        log.append(f"min-support {min_support:g}: {n_pre} -> {df['player_id'].n_unique()} players")

    if df["player_id"].n_unique() < 10:
        sys.exit("fewer than 10 players survive the filters — loosen them")

    df = df.with_columns((pl.col("bucket") + "__" + pl.col("end")).alias("feat"))
    features = [f"{b}__{e}" for b in buckets for e in ENDS]

    wide = df.pivot(values="deviation", index="player_id", on="feat",
                    aggregate_function="first")
    for f in features:
        if f not in wide.columns:
            sys.exit(f"expected feature column absent after pivot: {f}")
    wide = wide.select(["player_id", *features])

    n_pre = wide.height
    wide = wide.drop_nulls()
    if wide.height != n_pre:
        log.append(f"dropped {n_pre - wide.height} player(s) with incomplete coverage")

    extra = df.group_by("player_id").agg(
        pl.col("support").min().alias("min_support"),
        pl.col("support").sum().alias("tot_support"),
        pl.col("prior").first().alias("prior"),
    )
    wide = wide.join(extra, on="player_id", how="left").join(names, on="player_id", how="left")

    n_unnamed = wide.filter(pl.col("name").is_null()).height
    if n_unnamed:
        log.append(f"WARNING: {n_unnamed} of {wide.height} players still unnamed after map join")
    wide = wide.with_columns(pl.col("name").fill_null(pl.col("player_id")).alias("label"))

    X = wide.select(features).to_numpy().astype(np.float64)
    mu, sd = X.mean(axis=0), X.std(axis=0, ddof=1)
    if np.any(sd == 0):
        sys.exit(f"zero-variance feature(s): {[f for f, s in zip(features, sd) if s == 0]}")
    Z = (X - mu) / sd
    log.append("feature raw sd (pre-z, post-filter): " +
               ", ".join(f"{f} {s:.3f}" for f, s in zip(features, sd)))

    return wide, X, Z, features


def distance_matrices(Z: np.ndarray):
    """Euclidean (primary) and cosine (secondary) over the same z-scored space."""
    sq = np.sum(Z ** 2, axis=1)
    D2 = sq[:, None] + sq[None, :] - 2.0 * (Z @ Z.T)
    D = np.sqrt(np.maximum(D2, 0.0))

    norms = np.linalg.norm(Z, axis=1, keepdims=True)
    zero = norms.ravel() < 1e-12
    safe = norms.copy()
    safe[zero] = 1.0
    C = (Z / safe) @ (Z / safe).T
    C[zero, :] = np.nan
    C[:, zero] = np.nan

    np.fill_diagonal(D, np.inf)   # never return self
    np.fill_diagonal(C, np.nan)
    return D, C


def top_k_table(wide, D, C, k, metric):
    ids = wide["player_id"].to_list()
    labels = wide["label"].to_list()
    sup = wide["min_support"].to_list()
    rows = []
    for i in range(len(ids)):
        order = np.argsort(D[i]) if metric == "euclidean" else \
                np.argsort(-np.nan_to_num(C[i], nan=-np.inf))
        for rank, j in enumerate(order[:k], start=1):
            if not np.isfinite(D[i, j]):
                continue
            rows.append({
                "player_id": ids[i],
                "label": labels[i],
                "rank": rank,
                "neighbour_id": ids[j],
                "neighbour_label": labels[j],
                "distance": float(D[i, j]),
                "cosine": float(C[i, j]) if np.isfinite(C[i, j]) else None,
                "neighbour_min_support": sup[j],
            })
    return pl.DataFrame(rows)


def jaccard_at_k(a, b, k):
    ga = {p: set(g["neighbour_id"].to_list()[:k]) for p, g in a.group_by("player_id")}
    gb = {p: set(g["neighbour_id"].to_list()[:k]) for p, g in b.group_by("player_id")}
    shared = set(ga) & set(gb)
    if not shared:
        return float("nan"), 0
    vals = [len(ga[p] & gb[p]) / len(ga[p] | gb[p]) for p in shared if ga[p] or gb[p]]
    return float(np.mean(vals)), len(shared)


def run(window, key, buckets, k, metric, require_reliable, min_support, wh, rp):
    log = [f"window={window}  buckets={key} {buckets}  metric={metric}  "
           f"top_k={k}  require_reliable={require_reliable}  min_support={min_support:g}"]
    names = load_names(wh, log)
    df = load_long(window, wh)
    wide, X, Z, features = build_vectors(df, names, buckets, require_reliable, min_support, log)
    log.append(f"players in space: {wide.height}   dimensions: {len(features)}")

    D, C = distance_matrices(Z)
    nn = top_k_table(wide, D, C, k, metric)

    vec = wide.select(["player_id", "label", "name", "min_support", "tot_support",
                       "prior", *features])
    vec = vec.with_columns(**{f"z__{f}": pl.Series(Z[:, i]) for i, f in enumerate(features)})

    stem = f"{window}_{key}"
    wh.mkdir(parents=True, exist_ok=True)
    rp.mkdir(parents=True, exist_ok=True)
    nn.write_parquet(wh / f"similarity_{stem}.parquet")
    vec.write_parquet(wh / f"shotctx_vectors_{stem}.parquet")

    fd = D[np.isfinite(D)]
    log.append(f"distance: mean {fd.mean():.3f}  p05 {np.percentile(fd, 5):.3f}  "
               f"p50 {np.percentile(fd, 50):.3f}")
    log.append(f"vector norms: mean {np.linalg.norm(Z, axis=1).mean():.3f}  "
               f"min {np.linalg.norm(Z, axis=1).min():.3f}  "
               f"max {np.linalg.norm(Z, axis=1).max():.3f}")

    log.append("\nface validity — nearest neighbours:")
    for p in ["TAVARES", "FALL", "SLOUKAS", "HOWARD", "BALDWIN", "MUSA", "VESELY"]:
        hit = wide.filter(pl.col("label").str.contains(p))
        if hit.height == 0:
            log.append(f"  {p}: not in space (filtered out or absent from window)")
            continue
        pid = hit["player_id"][0]
        sub = nn.filter(pl.col("player_id") == pid).head(5)
        s = ", ".join(f"{r['neighbour_label']} (d={r['distance']:.2f})"
                      for r in sub.iter_rows(named=True))
        log.append(f"  {hit['label'][0]}: {s}")

    report = "\n".join(log)
    (rp / f"similarity_{stem}.txt").write_text(report + "\n")
    print(report)
    return nn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="dash", choices=["dash", "eval", "baseline"])
    ap.add_argument("--buckets", default="identified", choices=["identified", "all"])
    ap.add_argument("--metric", default="euclidean", choices=["euclidean", "cosine"])
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--min-support", type=float, default=0.0)
    ap.add_argument("--no-require-reliable", dest="require_reliable",
                    action="store_false", default=True)
    ap.add_argument("--warehouse", default="warehouse")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--compare", action="store_true",
                    help="run both bucket sets and report top-k agreement (Ch6 figure)")
    a = ap.parse_args()
    wh, rp = Path(a.warehouse), Path(a.reports)

    common = dict(k=a.top_k, metric=a.metric, require_reliable=a.require_reliable,
                  min_support=a.min_support, wh=wh, rp=rp)

    if a.compare:
        nn_id = run(a.window, "identified", BUCKETS_IDENTIFIED, **common)
        print("\n" + "=" * 70 + "\n")
        nn_all = run(a.window, "all", BUCKETS_ALL, **common)
        j, n = jaccard_at_k(nn_id, nn_all, a.top_k)
        msg = (f"\n{'=' * 70}\nAGREEMENT identified vs all buckets: "
               f"mean Jaccard@{a.top_k} = {j:.3f} over {n} shared players\n"
               f"NOTE the two runs have different populations: the reliability gate is\n"
               f"stricter over 8 cells than over 4, so 'all' is a subset. Jaccard is\n"
               f"computed on the intersection only.")
        print(msg)
        (rp / f"similarity_{a.window}_agreement.txt").write_text(msg + "\n")
    else:
        buckets = BUCKETS_IDENTIFIED if a.buckets == "identified" else BUCKETS_ALL
        run(a.window, a.buckets, buckets, **common)


if __name__ == "__main__":
    main()
