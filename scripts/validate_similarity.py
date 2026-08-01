#!/usr/bin/env python3
"""
validate_similarity.py — does the shot-context similarity space carry structure?

This decides whether Ch6 ships a tool or reports a negative result. Three tests:

  T1 STRUCTURE   PCA on the z-scored deviation matrix. If PC1 absorbs most of the
                 variance with same-sign loadings on every axis, the space has one
                 dimension ("deviates a lot / a little") and neighbours are ranked
                 by a single latent quantity rather than by shot-context shape.

  T2 QUALITY     corr(pairwise distance, |prior_i - prior_j|). The prior is each
                 player's overall RAPM. If this correlation is high the finder is
                 a leaderboard in disguise, which is precisely the failure mode the
                 deviation-not-value decision was meant to avoid. Ch5 reports
                 corr(deviation, overall) = -0.026 at the univariate level; this is
                 the multivariate version of the same check and it must stay low.

  T3 STABILITY   Top-k neighbour agreement between the dash and eval windows for
                 players present in both. This is the decisive test. A neighbour
                 set that does not survive a change of fitting window is not a
                 property of the players. NOTE the windows overlap (2021-2025 vs
                 2020-2024, four seasons shared), so this is a lenient test: high
                 agreement is weak evidence, but LOW agreement is strong evidence
                 against shipping.

Prerequisite — run the finder on both windows first:
  python3 scripts/build_similarity_finder.py --window dash
  python3 scripts/build_similarity_finder.py --window eval

Usage:
  python3 scripts/validate_similarity.py
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl

WH = Path("warehouse")
RP = Path("reports")
K = 10


def need(p: Path):
    if not p.exists():
        sys.exit(f"missing {p} — run build_similarity_finder.py for that window first")
    return p


def t1_structure(vec: pl.DataFrame, log: list[str]):
    zcols = [c for c in vec.columns if c.startswith("z__")]
    Z = vec.select(zcols).to_numpy()
    Zc = Z - Z.mean(axis=0)
    U, S, Vt = np.linalg.svd(Zc, full_matrices=False)
    var = S ** 2 / np.sum(S ** 2)
    log.append("T1 STRUCTURE — PCA on z-scored deviations")
    log.append(f"  explained variance: " + ", ".join(f"PC{i+1} {v:.3f}" for i, v in enumerate(var)))
    for i in range(min(3, len(var))):
        load = ", ".join(f"{c[3:]} {w:+.2f}" for c, w in zip(zcols, Vt[i]))
        log.append(f"  PC{i+1} loadings: {load}")
    same_sign = np.all(Vt[0] > 0) or np.all(Vt[0] < 0)
    log.append(f"  PC1 share {var[0]:.3f}, all-same-sign loadings: {same_sign}")
    if var[0] > 0.60 and same_sign:
        log.append("  VERDICT: one dominant general axis — space is close to unidimensional.")
    else:
        log.append("  VERDICT: multi-dimensional structure retained.")
    log.append("")
    return var[0]


def t2_quality(vec: pl.DataFrame, log: list[str]):
    zcols = [c for c in vec.columns if c.startswith("z__")]
    Z = vec.select(zcols).to_numpy()
    prior = vec["prior"].to_numpy()

    sq = np.sum(Z ** 2, axis=1)
    D = np.sqrt(np.maximum(sq[:, None] + sq[None, :] - 2 * (Z @ Z.T), 0.0))
    P = np.abs(prior[:, None] - prior[None, :])

    iu = np.triu_indices(len(prior), k=1)
    d, p = D[iu], P[iu]
    ok = np.isfinite(d) & np.isfinite(p)
    r = np.corrcoef(d[ok], p[ok])[0, 1]

    log.append("T2 QUALITY CONTAMINATION — distance vs |prior difference|")
    log.append(f"  pairs: {ok.sum()}   corr(distance, |dprior|) = {r:+.3f}")
    if abs(r) > 0.40:
        log.append("  VERDICT: distance substantially tracks overall-rating gap. The finder")
        log.append("           is partly a leaderboard. Do not ship without addressing.")
    elif abs(r) > 0.20:
        log.append("  VERDICT: mild contamination — report the number, ship with the caveat.")
    else:
        log.append("  VERDICT: clean — distance is not a proxy for overall rating.")
    log.append("")
    return r


def t3_stability(log: list[str]):
    a = pl.read_parquet(need(WH / "similarity_dash_identified.parquet"))
    b = pl.read_parquet(need(WH / "similarity_eval_identified.parquet"))

    # polars group_by yields the key as a TUPLE. Unwrapping it is not cosmetic:
    # keeping the tuple made every set intersection below compare tuples against
    # plain neighbour-id strings, producing an empty list and a nan mean, which
    # then slipped past the `<` guard and printed a false positive verdict.
    ga = {p[0]: g.sort("rank")["neighbour_id"].to_list()[:K]
          for p, g in a.group_by("player_id")}
    gb = {p[0]: g.sort("rank")["neighbour_id"].to_list()[:K]
          for p, g in b.group_by("player_id")}
    shared = sorted(set(ga) & set(gb))

    log.append("T3 STABILITY — dash vs eval neighbour sets")
    log.append(f"  dash players {len(ga)}, eval players {len(gb)}, shared {len(shared)}")
    if len(shared) < 20:
        log.append("  too few shared players to judge; treat as inconclusive.")
        log.append("")
        return float("nan")

    jac, top1 = [], 0
    for p in shared:
        sa, sb = set(ga[p]), set(gb[p])
        if sa or sb:
            jac.append(len(sa & sb) / len(sa | sb))
        if ga[p] and gb[p] and ga[p][0] == gb[p][0]:
            top1 += 1

    m = float(np.mean(jac)) if jac else float("nan")
    log.append(f"  mean Jaccard@{K} = {m:.3f}")
    log.append(f"  identical nearest neighbour: {top1}/{len(shared)} = {top1/len(shared):.3f}")
    log.append(f"  random-chance Jaccard@{K} baseline ~ {K/len(shared):.3f}")
    if not np.isfinite(m):
        log.append("  VERDICT: INCONCLUSIVE — no comparable pairs. Do not read this as a pass.")
    elif m < 2 * (K / len(shared)):
        log.append("  VERDICT: neighbour sets do not replicate across windows. The finder")
        log.append("           describes the fit, not the players. Report as a negative result.")
    elif m < 0.35:
        log.append("  VERDICT: weak replication. Ship only with the instability stated, or")
        log.append("           present neighbourhoods as clusters rather than ranked lists.")
    else:
        log.append("  VERDICT: neighbour sets replicate — the structure is a player property.")
    log.append("")
    return m


def main():
    log = ["validate_similarity.py — Ch6 ship/no-ship evidence", "=" * 60, ""]
    vec = pl.read_parquet(need(WH / "shotctx_vectors_dash_identified.parquet"))
    log.append(f"dash identified space: {vec.height} players")
    log.append("")

    pc1 = t1_structure(vec, log)
    r = t2_quality(vec, log)
    stab = t3_stability(log)

    log.append("=" * 60)
    log.append("SUMMARY")
    log.append(f"  PC1 share            {pc1:.3f}")
    log.append(f"  corr(dist,|dprior|)  {r:+.3f}")
    log.append(f"  dash-eval Jaccard@{K}  {stab:.3f}")
    log.append("")
    log.append("  Ship the finder only if T2 is clean-to-mild AND T3 replicates above")
    log.append("  roughly twice chance. Otherwise Ch6 reports the negative result, which")
    log.append("  is a defensible chapter: it establishes that per-context deviations do")
    log.append("  not support a stable player-similarity metric at this sample depth,")
    log.append("  consistent with the three-point non-identifiability already in Ch5.")

    out = "\n".join(log)
    RP.mkdir(parents=True, exist_ok=True)
    (RP / "similarity_validation.txt").write_text(out + "\n")
    print(out)


if __name__ == "__main__":
    main()