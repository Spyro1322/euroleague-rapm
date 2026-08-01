#!/usr/bin/env python3
"""
decide_tab3_format.py — is there a stable output format in the shot-context space?

Context. validate_similarity.py established:
  T1 four near-equal PCs (0.31/0.28/0.21/0.20); PC1 is at_rim_off vs mid_range_off,
     i.e. Ch5's rim-tilt axis recovered without supervision.
  T2 corr(distance, |prior difference|) = +0.059 over 65,341 pairs — the space is
     not a leaderboard in disguise.
  T3 mean Jaccard@10 between the dash and eval windows = 0.147 against a chance
     baseline of 0.034. Read against the fact that those windows share four of
     five seasons, 85% turnover in the top ten is a FAILURE, not a pass. A ranked
     similarity list is not a defensible deliverable.

  BUT the single nearest neighbour agreed 27/293 = 9.2% against 0.34% chance (27x),
  so the head of the list is far more stable than the tail.

Two candidate formats are therefore tested here.

  F1 SHORT LISTS   Jaccard at K = 1, 3, 5, 10. If agreement rises sharply as K
                   falls, the signal lives in the nearest few and Tab 3 ships a
                   top-3 rather than a top-10.

  F2 ARCHETYPES    K-means on the z-scored space, fitted separately per window,
                   compared by adjusted Rand index on the shared players. A cluster
                   label is a coarser claim than a rank, so it should survive more.
                   ARI is chance-corrected: 0 is random, 1 is identical partitions.

DECISION RULE (apply it, do not relitigate):
  - ARI >= 0.30 at some k in 3..8      -> Tab 3 ships as archetypes.
  - else Jaccard@3 >= 0.40             -> Tab 3 ships as a top-3 short list.
  - else                               -> cut Tab 3. Ch6 reports the negative
                                          result and the hours go to Ch9.

Prerequisite:
  python3 scripts/build_similarity_finder.py --window dash
  python3 scripts/build_similarity_finder.py --window eval

Usage:
  python3 scripts/decide_tab3_format.py
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score

WH = Path("warehouse")
RP = Path("reports")
SEED = 42


def need(p: Path) -> Path:
    if not p.exists():
        sys.exit(f"missing {p} — run build_similarity_finder.py for that window first")
    return p


def neighbour_map(path: Path, k: int) -> dict[str, list[str]]:
    df = pl.read_parquet(path)
    # polars group_by returns the key as a tuple — unwrap it, or every set
    # intersection downstream silently compares tuples against strings.
    return {p[0]: g.sort("rank")["neighbour_id"].to_list()[:k]
            for p, g in df.group_by("player_id")}


def f1_short_lists(log: list[str]) -> dict[int, float]:
    a_path = need(WH / "similarity_dash_identified.parquet")
    b_path = need(WH / "similarity_eval_identified.parquet")

    log.append("F1 SHORT LISTS — neighbour agreement as a function of K")
    log.append("   K   Jaccard   chance   ratio   same-1st")
    out = {}
    for k in (1, 3, 5, 10):
        ga, gb = neighbour_map(a_path, k), neighbour_map(b_path, k)
        shared = sorted(set(ga) & set(gb))
        if len(shared) < 20:
            log.append(f"  {k:2d}   too few shared players")
            continue
        jac = []
        same1 = 0
        for p in shared:
            sa, sb = set(ga[p]), set(gb[p])
            if sa or sb:
                jac.append(len(sa & sb) / len(sa | sb))
            if ga[p] and gb[p] and ga[p][0] == gb[p][0]:
                same1 += 1
        m = float(np.mean(jac)) if jac else float("nan")
        chance = k / len(shared)
        out[k] = m
        log.append(f"  {k:2d}   {m:.3f}     {chance:.3f}    {m/chance:5.1f}x   "
                   f"{same1/len(shared):.3f}")
    log.append("")
    return out


def load_space(window: str):
    vec = pl.read_parquet(need(WH / f"shotctx_vectors_{window}_identified.parquet"))
    zcols = sorted(c for c in vec.columns if c.startswith("z__"))
    return vec["player_id"].to_list(), vec.select(zcols).to_numpy(), zcols


def f2_archetypes(log: list[str]) -> dict[int, float]:
    ids_a, Za, zc_a = load_space("dash")
    ids_b, Zb, zc_b = load_space("eval")
    if zc_a != zc_b:
        sys.exit(f"feature mismatch between windows: {zc_a} vs {zc_b}")

    idx_a = {p: i for i, p in enumerate(ids_a)}
    idx_b = {p: i for i, p in enumerate(ids_b)}
    shared = sorted(set(idx_a) & set(idx_b))
    log.append(f"F2 ARCHETYPES — K-means per window, ARI on {len(shared)} shared players")
    log.append("   k    ARI    interpretation")

    ia = [idx_a[p] for p in shared]
    ib = [idx_b[p] for p in shared]

    out = {}
    for k in range(3, 9):
        la = KMeans(n_clusters=k, n_init=25, random_state=SEED).fit_predict(Za)
        lb = KMeans(n_clusters=k, n_init=25, random_state=SEED).fit_predict(Zb)
        ari = adjusted_rand_score(np.asarray(la)[ia], np.asarray(lb)[ib])
        out[k] = ari
        tag = "stable" if ari >= 0.30 else ("marginal" if ari >= 0.15 else "unstable")
        log.append(f"  {k:2d}   {ari:+.3f}   {tag}")
    log.append("")
    return out


def describe_best(k: int, log: list[str]):
    """Profile the archetypes at the chosen k so Ch6 can name them."""
    ids, Z, zcols = load_space("dash")
    vec = pl.read_parquet(WH / "shotctx_vectors_dash_identified.parquet")
    lab = KMeans(n_clusters=k, n_init=25, random_state=SEED).fit_predict(Z)
    vec = vec.with_columns(pl.Series("archetype", lab))
    vec.write_parquet(WH / "shotctx_archetypes_dash.parquet")

    log.append(f"ARCHETYPE PROFILES at k={k} (dash window, mean z per axis)")
    prof = (vec.group_by("archetype")
            .agg(pl.len().alias("n"), *[pl.col(c).mean().alias(c) for c in sorted(zcols)])
            .sort("archetype"))
    for r in prof.iter_rows(named=True):
        axes = ", ".join(f"{c[3:]} {r[c]:+.2f}" for c in sorted(zcols))
        members = (vec.filter(pl.col("archetype") == r["archetype"])
                   .sort("tot_support", descending=True)["label"].to_list()[:6])
        log.append(f"  A{r['archetype']} (n={r['n']}): {axes}")
        log.append(f"      e.g. {', '.join(members)}")
    log.append("")
    log.append("  written: warehouse/shotctx_archetypes_dash.parquet")
    log.append("")


def main():
    log = ["decide_tab3_format.py — O4 output-format decision", "=" * 62, ""]
    jac = f1_short_lists(log)
    ari = f2_archetypes(log)

    best_k = max(ari, key=ari.get) if ari else None
    best_ari = ari[best_k] if best_k else float("nan")
    j3 = jac.get(3, float("nan"))

    log.append("=" * 62)
    log.append("DECISION")
    if best_k is not None and best_ari >= 0.30:
        log.append(f"  ARCHETYPES. Best ARI {best_ari:+.3f} at k={best_k} (>= 0.30).")
        log.append("  Tab 3 ships shot-context archetypes, not a similarity ranking.")
        log.append("  Ch6 reports both: rankings unstable across windows, groupings stable.")
        describe_best(best_k, log)
    elif np.isfinite(j3) and j3 >= 0.40:
        log.append(f"  SHORT LIST. Jaccard@3 = {j3:.3f} (>= 0.40).")
        log.append("  Tab 3 ships a top-3 with the instability of the longer tail stated.")
    else:
        log.append(f"  CUT TAB 3. Best ARI {best_ari:+.3f} at k={best_k}; Jaccard@3 {j3:.3f}.")
        log.append("  Neither format survives a change of fitting window. Ch6 reports the")
        log.append("  negative result: per-context deviations carry genuine multi-dimensional")
        log.append("  structure (four near-equal PCs, PC1 = the rim-tilt axis, and no")
        log.append("  contamination by overall rating) but do not support a stable")
        log.append("  player-similarity metric at this sample depth. Reallocate the hours")
        log.append("  to Ch9, which has more genuine material than Ch6 would have had.")

    out = "\n".join(log)
    RP.mkdir(parents=True, exist_ok=True)
    (RP / "tab3_format_decision.txt").write_text(out + "\n")
    print(out)


if __name__ == "__main__":
    main()
