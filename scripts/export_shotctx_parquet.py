"""
scripts/export_shotctx_parquet.py

Turns the per-bucket fits into the long parquet Tab 2 renders. No fitting here.

SIGN NORMALISATION — read this before changing anything
The design puts +1 on both the offensive and the defensive five while y is points
scored BY the offence. So a raw defensive coefficient is NEGATIVE-for-good, and
the prior is mu_def = -DRAPM. The leaderboard, and every number a reader will
compare against, is POSITIVE-for-good on both ends.

This script therefore negates the defensive end on export:
    value_display = -beta_def        prior_display = -mu_def = +DRAPM
so that on both ends a larger number means the player helped, and a bucket value
is directly comparable to that player's overall ORAPM / DRAPM. Getting this wrong
inverts every defensive spoke while looking entirely plausible, so the script
asserts the relationship against the leaderboard before writing anything.

RELIABILITY GATE
`support` from the design is X^T w -- for each player, total bucket attempts in
lineup-states they were on court for. That is the right measure for a plus-minus
estimate (on-court exposure, not personal shot volume). A bucket is marked
unreliable for a player when support falls below --min-support.

Support is NOT the same question as identifiability. Support says how much data
backs one player's estimate in a bucket; identifiability says whether the bucket
is estimable at all. A bucket with no measurable signal must not be rendered at
ANY support level, so the two suppression reasons are carried separately and the
dashboard states them differently.

SIGNAL VERDICT
Taken from the unshrunk correlation between each bucket's raw coefficients and
that player's overall ORAPM / DRAPM (in the fit report). A pure-noise estimate
cannot correlate with an independently fitted quantity, and the measure needs no
variance normalisation. Week 6, consistent across all three windows:
    at_rim            |corr| ~0.47-0.48   STRONG
    mid_range         |corr| ~0.34-0.37   STRONG
    above_break_three |corr| ~0.05-0.10   NONE
    corner_three      |corr| ~0.02-0.05   NONE
Two-point buckets measure shot creation and rim protection, which are repeatable
on-court skills. Three-point buckets measure three-point outcomes, which largely
are not repeatable at lineup level -- a known plus-minus result, reproduced here.

OUTPUT  warehouse/shotctx_{window}.parquet, one row per player x bucket x end
    player_id, name, poss   identity + overall exposure
    bucket, end             'off' | 'def'
    value                   fitted rating, positive-for-good, pts/100 of that type
    prior                   shrinkage target = that player's overall O/D RAPM
    deviation               value - prior : THE FINDING. Zero means the model found
                            nothing beyond the player's overall level.
    support                 bucket attempts while on court
    reliable                support >= min_support
    league_mean             that bucket's league average pts/100
    alpha                   the fit's regularisation strength
"""

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

W = Path("warehouse")
R = Path("reports")
BUCKETS = ["at_rim", "mid_range", "corner_three", "above_break_three"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--min-support", type=float, default=150.0,
                    help="bucket attempts on court below which a value is marked "
                         "unreliable and suppressed in the dashboard")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    prefix = args.prefix or f"shotctx_{args.window}"
    out_path = Path(args.out or (W / f"shotctx_{args.window}.parquet"))

    fits = sorted(W.glob(f"{prefix}_*_fit.npz"))
    if not fits:
        raise SystemExit(f"no fits found matching {prefix}_*_fit.npz")

    found = [p.name[len(prefix) + 1:-len("_fit.npz")] for p in fits]
    stale = [b for b in found if b not in BUCKETS]
    if stale:
        raise SystemExit(
            f"  FATAL: stale fit(s) for non-taxonomy bucket(s) {stale}.\n"
            f"  These are pre-Week-6 artifacts. Re-run build_shotctx_design.py for\n"
            f"  this window (it purges them) before exporting -- otherwise makes-only\n"
            f"  situation buckets reach the dashboard."
        )
    print(f"window {args.window}: buckets {found}")

    dmeta = np.load(W / f"{prefix}_{found[0]}_design.npz", allow_pickle=True)
    lb_stem = str(dmeta["leaderboard_stem"])
    lb = pl.read_parquet(W / f"{lb_stem}.parquet")
    print(f"  leaderboard: {lb_stem}.parquet ({lb.height} players)")
    lb_small = lb.select(["player_id", "name", "poss", "ORAPM", "DRAPM"])

    records, fit_summary = [], []
    for bucket in found:
        f = np.load(W / f"{prefix}_{bucket}_fit.npz", allow_pickle=True)
        d = np.load(W / f"{prefix}_{bucket}_design.npz", allow_pickle=True)

        beta, mu = f["beta"], f["mu"]
        pids = [str(p) for p in f["player_ids"]]
        pcols = f["player_cols"]
        ob, db = int(f["off_base"]), int(f["def_base"])
        alpha = float(f["alpha"])
        ybar = float(f["ybar"]) if "ybar" in f.files else float("nan")
        support = f["support"] if "support" in f.files else d["support"]

        # Signal verdict, carried into the parquet because the deployment mirror
        # ships only parquet -- reports/ never reaches the dashboard.
        c_off = float(f["corr_off"]) if "corr_off" in f.files else float("nan")
        c_def = float(f["corr_def"]) if "corr_def" in f.files else float("nan")
        if c_off != c_off or c_def != c_def:
            rp = R / f"{prefix}_fit_report.json"
            if rp.exists():
                for rr in json.loads(rp.read_text()):
                    if rr["bucket"] == bucket:
                        c_off = float(rr.get("corr_off", float("nan")))
                        c_def = float(rr.get("corr_def", float("nan")))
        sig = max(abs(c_off) if c_off == c_off else 0.0,
                  abs(c_def) if c_def == c_def else 0.0)
        verdict = "STRONG" if sig >= 0.25 else ("WEAK" if sig >= 0.10 else "NONE")
        fit_summary.append(dict(bucket=bucket, alpha=alpha, league_mean=ybar,
                                signal=sig, verdict=verdict))

        for pid, c in zip(pids, pcols):
            c = int(c)
            # sign = -1 on defence: negative-for-good -> positive-for-good
            for end, base, sign in (("off", ob, 1.0), ("def", db, -1.0)):
                idx = base + c
                records.append(dict(
                    player_id=pid, bucket=bucket, end=end,
                    value=float(sign * beta[idx]),
                    prior=float(sign * mu[idx]),
                    support=float(support[idx]),
                    league_mean=ybar, alpha=alpha,
                    signal=sig, verdict=verdict,
                ))

    df = pl.DataFrame(records).with_columns(
        (pl.col("value") - pl.col("prior")).alias("deviation")
    ).join(lb_small, on="player_id", how="left")

    # ---- sign assertions, against evidence the export did not construct
    for end, col in (("def", "DRAPM"), ("off", "ORAPM")):
        chk = df.filter((pl.col("end") == end) & pl.col(col).is_not_null())
        if not chk.height:
            continue
        err = float((chk["prior"] - chk[col]).abs().max())
        print(f"  sign check: max |prior_{end} - {col}| = {err:.6f}")
        if err > 1e-4:
            raise SystemExit(
                f"  FATAL: exported {end} prior does not equal {col}. The sign\n"
                f"  normalisation is wrong -- every {end} spoke would be inverted.\n"
                f"  Confirm the fit ran with --force-signs +1,-1."
            )
    print("    OK — both ends positive-for-good and matching the leaderboard.")

    df = df.with_columns(
        (pl.col("support") >= args.min_support).alias("reliable")
    ).select([
        "player_id", "name", "poss", "bucket", "end",
        "value", "prior", "deviation", "support", "reliable",
        "signal", "verdict", "league_mean", "alpha",
    ])

    print(f"\n  rows: {df.height:,}  players: {df['player_id'].n_unique():,}")
    unnamed = df.filter(pl.col("name").is_null())["player_id"].n_unique()
    if unnamed:
        print(f"  {unnamed} player(s) absent from the leaderboard (below its display "
              f"floor); they carry prior 0 and are not selectable in the dashboard.")

    print("\n  support / reliability by bucket (offensive end):")
    rel = (df.filter(pl.col("end") == "off").group_by("bucket").agg([
        pl.len().alias("players"),
        pl.col("reliable").sum().alias("reliable"),
        pl.col("support").median().alias("median_support"),
        pl.col("deviation").std().alias("deviation_sd"),
    ]).sort("median_support", descending=True))
    print(rel)

    print("\n  signal verdict per bucket (unshrunk corr with overall RAPM):")
    v = (df.group_by("bucket").agg([
        pl.col("signal").first().alias("signal"),
        pl.col("verdict").first().alias("verdict"),
    ]).sort("signal", descending=True))
    print(v)
    print("  Buckets marked NONE are rendered as 'no measurable effect' rather than")
    print("  as a value. See scripts/assess_identifiability.py for the derivation.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path)
    print(f"\n  wrote {out_path}")

    R.mkdir(exist_ok=True)
    (R / f"shotctx_{args.window}_export.json").write_text(json.dumps(dict(
        window=args.window, min_support=args.min_support, buckets=fit_summary,
        rows=df.height, players=int(df["player_id"].n_unique()),
    ), indent=2))
    print(f"  wrote reports/shotctx_{args.window}_export.json")


if __name__ == "__main__":
    main()