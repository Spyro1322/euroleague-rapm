"""
scripts/fit_shotctx_rapm.py

Fits shot-context RAPM per bucket, shrinking each (player, bucket, end) coefficient
toward that player's OVERALL RAPM from the same window's validated leaderboard.

WHY SHRINK TOWARD OVERALL RATHER THAN ZERO
A bucket sees a fraction of a player's possessions, so an unshrunk per-bucket
rating is dominated by noise. Shrinking toward zero would say "absent evidence,
this player is league-average at rim finishing" — but we have better information
than that: his overall rating. Shrinking toward it says "absent evidence, this
player is as good at rim finishing as he is generally," which is both a stronger
prior and the thing the radar's reference ring depends on. Deviation from the
ring is then the actual finding.

Implemented by reparametrising. To shrink beta toward mu instead of 0:
    min ||y - X b||_w^2 + a||b - mu||^2
  = min ||(y - X mu) - X c||_w^2 + a||c||^2       with c = b - mu
so an ordinary weighted ridge on the residualised target, then b = c + mu.

SIGN CONVENTION IS CALIBRATED, NOT ASSUMED
The design puts +1 on both the five offensive and the five defensive players, and
y is points scored BY the offense. A good defender therefore carries a NEGATIVE
raw coefficient. But the leaderboard reports DRAPM positive-for-good. Which means
mu for the defensive block is -DRAPM, not +DRAPM — unless the base fit used a
different convention.

Getting this backwards would shrink every good defender toward the wrong pole and
produce a plausible-looking, entirely inverted radar. So rather than assume, the
script first fits UNSHRUNK (mu = 0) and correlates the raw coefficients against
the leaderboard's ORAPM and DRAPM. The signs of those correlations determine the
convention empirically, and the script refuses to continue if the evidence is
ambiguous.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl
from scipy import sparse
from scipy.sparse.linalg import lsqr
from sklearn.model_selection import GroupKFold

W = Path("warehouse")
R = Path("reports")


def load_design(stem: str):
    """
    Returns X with an intercept column appended, y weighted-centred, and ybar.

    Centring y and fitting an unpenalised intercept are complementary: centring
    puts the target on a deviation scale so the shrinkage prior (overall RAPM,
    itself a deviation from average) is in the same units, and the intercept
    absorbs whatever level remains rather than letting it leak into the players.
    """
    meta = np.load(W / f"{stem}_design.npz", allow_pickle=True)
    X = sparse.load_npz(W / f"{stem}_design.X.npz").tocsr()
    y, w = meta["y"], meta["w"]
    ybar = float(np.average(y, weights=w))
    return add_intercept(X), y - ybar, ybar, meta


def add_intercept(X):
    """
    Append a column of ones. Each bucket has its own league-average efficiency
    level (~129 pts/100 at the rim, ~80 mid-range). Without an intercept that
    level is absorbed into the ten player coefficients on every row, so each
    coefficient comes out as an absolute efficiency rather than a deviation from
    average -- roughly level/10 added to every player. The radar would then sit
    nowhere near the overall-RAPM reference ring while looking perfectly plausible.
    """
    ones = sparse.csr_matrix(np.ones((X.shape[0], 1)))
    return sparse.hstack([X, ones]).tocsr()


def ridge_shrunk(X, y, w, mu, alpha, n_unpenalised=1):
    """
    Weighted ridge shrunk toward mu, with the trailing `n_unpenalised` columns
    (the intercept) excluded from the penalty. Penalising an intercept would
    shrink the bucket's baseline efficiency toward zero and push the difference
    back into the player coefficients, reintroducing the bug the intercept exists
    to remove.
    """
    sw = np.sqrt(w)
    Xw = X.multiply(sw[:, None]).tocsr()
    target = sw * (y - X @ mu)
    p = Xw.shape[1]
    pen = np.full(p, np.sqrt(alpha))
    if n_unpenalised:
        pen[-n_unpenalised:] = 0.0
    A = sparse.vstack([Xw, sparse.diags(pen).tocsr()]).tocsr()
    b = np.concatenate([target, np.zeros(p)])
    out = lsqr(A, b, atol=1e-9, btol=1e-9, iter_lim=8000)
    return out[0] + mu, out


def cv_alpha(X, y, w, groups, mu, alphas, n_splits=5):
    gkf = GroupKFold(n_splits=n_splits)
    best, rows = None, []
    for a in alphas:
        errs = []
        for tr, va in gkf.split(X, y, groups):
            beta, _ = ridge_shrunk(X[tr], y[tr], w[tr], mu, a)
            resid = y[va] - X[va] @ beta
            errs.append(np.sqrt(np.average(resid ** 2, weights=w[va])))
        m = float(np.mean(errs))
        rows.append((float(a), m))
        if best is None or m < best[1]:
            best = (float(a), m)
    return best, rows


def calibrate_signs(X, y, w, groups, off_slice, def_slice, o_rapm, d_rapm,
                    alpha_probe):
    """
    Fit unshrunk and correlate raw coefficients with the leaderboard, to determine
    whether mu_off = +ORAPM / mu_def = -DRAPM (the expected convention) or otherwise.
    """
    p = X.shape[1]
    beta0, _ = ridge_shrunk(X, y, w, np.zeros(p), alpha_probe)
    b_off = beta0[off_slice]
    b_def = beta0[def_slice]

    ok_o = np.isfinite(o_rapm) & np.isfinite(b_off)
    ok_d = np.isfinite(d_rapm) & np.isfinite(b_def)

    def corr(a, b):
        if a.size < 10 or np.std(a) == 0 or np.std(b) == 0:
            return float("nan")
        return float(np.corrcoef(a, b)[0, 1])

    c_off = corr(b_off[ok_o], o_rapm[ok_o])
    c_def = corr(b_def[ok_d], d_rapm[ok_d])

    print(f"    unshrunk corr(raw_off, ORAPM) = {c_off:+.4f}")
    print(f"    unshrunk corr(raw_def, DRAPM) = {c_def:+.4f}")

    sign_off = 1.0 if c_off >= 0 else -1.0
    sign_def = 1.0 if c_def >= 0 else -1.0
    return sign_off, sign_def, c_off, c_def


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True)
    ap.add_argument("--buckets", nargs="*", default=None,
                    help="default: every bucket design found for this window")
    ap.add_argument("--prefix", default=None,
                    help="design prefix, default shotctx_{window}")
    ap.add_argument("--alpha", type=float, default=None,
                    help="pin one alpha for all buckets")
    ap.add_argument("--cv", action="store_true",
                    help="select alpha per bucket by GroupKFold CV over the "
                         "(Season*100000+Gamecode) key")
    ap.add_argument("--alpha-grid", default="1,3.16,10,31.6,100,316,1000,3162,10000")
    ap.add_argument("--force-signs", default=None, metavar="OFF,DEF",
                    help="pin the sign convention instead of calibrating per bucket, "
                         "e.g. --force-signs +1,-1 . Recommended once the convention "
                         "has been established from the highest-attempt buckets: "
                         "per-bucket calibration is noise-driven on thin buckets.")
    ap.add_argument("--probe-alpha", type=float, default=100.0,
                    help="alpha used only for the unshrunk sign-calibration fit")
    ap.add_argument("--out-prefix", default=None)
    args = ap.parse_args()

    forced = None
    if args.force_signs:
        try:
            a, b = args.force_signs.split(",")
            forced = (float(a), float(b))
        except Exception:
            raise SystemExit("--force-signs must look like +1,-1")
        if set(forced) - {1.0, -1.0}:
            raise SystemExit("--force-signs values must each be +1 or -1")

    prefix = args.prefix or f"shotctx_{args.window}"
    out_prefix = args.out_prefix or prefix

    if args.alpha is None and not args.cv:
        raise SystemExit("Pass --alpha to pin, or --cv to select. No silent default.")

    buckets = args.buckets
    if not buckets:
        buckets = sorted(
            p.name[len(prefix) + 1:-len("_design.npz")]
            for p in W.glob(f"{prefix}_*_design.npz"))
    if not buckets:
        raise SystemExit(f"No designs found matching {prefix}_*_design.npz")
    print(f"WINDOW {args.window}  buckets: {buckets}")

    # ---- leaderboard: the shrinkage target
    first = np.load(W / f"{prefix}_{buckets[0]}_design.npz", allow_pickle=True)
    lb_stem = str(first["leaderboard_stem"])
    lb = pl.read_parquet(W / f"{lb_stem}.parquet")
    print(f"  shrinkage target: {lb_stem}.parquet ({lb.height} players)")
    lb_map = {r["player_id"]: (r["ORAPM"], r["DRAPM"]) for r in lb.iter_rows(named=True)}

    results, report = {}, []
    for bucket in buckets:
        stem = f"{prefix}_{bucket}"
        X, y, ybar, meta = load_design(stem)
        w, groups = meta["w"], meta["groups"]
        pids = [str(p) for p in meta["player_ids"]]
        pcols = meta["player_cols"]
        n_players = int(meta["n_players"])
        off_base, def_base = int(meta["off_base"]), int(meta["def_base"])

        print(f"\n  [{bucket}]  X={X.shape}  attempts={w.sum():,.0f}  "
              f"att/player={w.sum()/n_players:.1f}")
        print(f"    league mean: {ybar:.2f} pts/100 (removed; coefficients are "
              f"deviations from it)")

        # align leaderboard values to design columns
        o_rapm = np.full(n_players, np.nan)
        d_rapm = np.full(n_players, np.nan)
        hit = 0
        for pid, c in zip(pids, pcols):
            v = lb_map.get(pid)
            if v is not None:
                o_rapm[c], d_rapm[c] = float(v[0]), float(v[1])
                hit += 1
        print(f"    leaderboard match: {hit}/{n_players} players")
        if hit < n_players:
            print(f"    {n_players-hit} design players absent from the leaderboard "
                  f"(below its display floor); they shrink toward 0 instead of "
                  f"their overall rating.")

        off_slice = slice(off_base, off_base + n_players)
        def_slice = slice(def_base, def_base + n_players)

        # ---- sign convention
        print("    sign convention (unshrunk diagnostic fit):")
        s_off, s_def, c_off, c_def = calibrate_signs(
            X, y, w, groups, off_slice, def_slice, o_rapm, d_rapm, args.probe_alpha)
        if forced is not None:
            if (s_off, s_def) != forced:
                print(f"    this bucket's calibration says ({s_off:+.0f},{s_def:+.0f}) "
                      f"but --force-signs pins ({forced[0]:+.0f},{forced[1]:+.0f}); "
                      f"using the pinned value.")
            s_off, s_def = forced
        if not np.isfinite(c_off) or not np.isfinite(c_def):
            raise SystemExit(
                "    Sign calibration produced a non-finite correlation. Too few "
                "players or a degenerate design; resolve before fitting.")
        if forced is None and (abs(c_off) < 0.05 or abs(c_def) < 0.05):
            print(f"    !! WARNING: |corr| below 0.05 on at least one end. The raw "
                  f"per-bucket coefficients barely track the overall ratings, so the "
                  f"sign is not well determined by this bucket. Falling back to the "
                  f"expected convention (+ORAPM, -DRAPM). Verify against a bucket "
                  f"with more attempts before trusting this bucket's output.")
            s_off, s_def = 1.0, -1.0
        print(f"    -> mu_off = {s_off:+.0f} * ORAPM,  mu_def = {s_def:+.0f} * DRAPM")

        mu = np.zeros(X.shape[1])   # last entry is the intercept: prior 0
        mu[off_slice] = np.nan_to_num(s_off * o_rapm, nan=0.0)
        mu[def_slice] = np.nan_to_num(s_def * d_rapm, nan=0.0)

        # ---- alpha
        if args.cv:
            grid = [float(a) for a in args.alpha_grid.split(",")]
            print(f"    CV over {len(grid)} alphas, grouped by game:")
            (a_best, rmse), curve = cv_alpha(X, y, w, groups, mu, grid)
            for a, m in curve:
                mark = " <-" if a == a_best else ""
                print(f"      alpha={a:>10.2f}  rmse={m:.4f}{mark}")
            if a_best == grid[0] or a_best == grid[-1]:
                print(f"    !! alpha selected at the edge of the grid ({a_best}). "
                      f"Widen --alpha-grid; the optimum may lie outside it.")
            alpha = a_best
        else:
            alpha = args.alpha
            print(f"    pinned alpha={alpha}")

        beta, out = ridge_shrunk(X, y, w, mu, alpha)
        print(f"    lsqr istop={out[1]} iters={out[2]}")

        intercept = float(beta[-1])
        print(f"    fitted intercept: {intercept:+.3f} "
              f"(should be near 0 after centring; a large value means the "
              f"level is still leaking)")
        b_off, b_def = beta[off_slice], beta[def_slice]
        dev_off = b_off - mu[off_slice]
        dev_def = b_def - mu[def_slice]
        print(f"    fitted off: mean={b_off.mean():+.3f} sd={b_off.std():.3f}   "
              f"deviation from prior sd={dev_off.std():.3f}")
        print(f"    fitted def: mean={b_def.mean():+.3f} sd={b_def.std():.3f}   "
              f"deviation from prior sd={dev_def.std():.3f}")
        if dev_off.std() < 1e-3 and dev_def.std() < 1e-3:
            print("    !! Coefficients are essentially identical to the prior: alpha is "
                  "so large that this bucket contributes nothing. The radar would show "
                  "a perfect ring. Lower alpha or accept that this bucket is "
                  "unidentified and suppress it in the dashboard.")

        results[bucket] = dict(
            beta=beta, mu=mu, alpha=alpha, sign_off=s_off, sign_def=s_def,
            support=meta["support"], player_ids=np.array(pids, dtype=object),
            intercept=intercept, ybar=ybar,
            player_cols=pcols, n_players=n_players,
            off_base=off_base, def_base=def_base,
        )
        report.append(dict(
            bucket=bucket, alpha=alpha, rows=int(X.shape[0]),
            attempts=float(w.sum()), corr_off=c_off, corr_def=c_def,
            sign_off=s_off, sign_def=s_def,
            dev_off_sd=float(dev_off.std()), dev_def_sd=float(dev_def.std()),
            ybar=ybar, intercept=intercept,
        ))

    for bucket, r in results.items():
        np.savez(W / f"{out_prefix}_{bucket}_fit.npz", **r)
    print(f"\n  wrote {len(results)} fit(s): warehouse/{out_prefix}_<bucket>_fit.npz")

    R.mkdir(exist_ok=True)
    (R / f"{out_prefix}_fit_report.json").write_text(json.dumps(report, indent=2))
    print(f"  reports/{out_prefix}_fit_report.json")

    # Cross-bucket identifiability is assessed by scripts/assess_identifiability.py.
    # An earlier version compared RAW deviation sd against attempts here; that is
    # confounded by outcome variance (3-pt buckets have y sd ~140 vs ~75 for 2-pt),
    # so it measured shot variance and reported the sign of the verdict backwards.
    print("\n  per-bucket signal (unshrunk corr with overall RAPM):")
    for r in sorted(report, key=lambda x: -max(abs(x["corr_off"]), abs(x["corr_def"]))):
        s_ = max(abs(r["corr_off"]), abs(r["corr_def"]))
        tag = "STRONG" if s_ >= 0.25 else ("WEAK" if s_ >= 0.10 else "NONE")
        print(f"    {r['bucket']:20} |corr|={s_:.3f}  {tag}")
    print("  Run scripts/assess_identifiability.py for the full assessment.")

    signs = {(r["sign_off"], r["sign_def"]) for r in report}
    if len(signs) > 1:
        print("\n  !! BUCKETS DISAGREE ON SIGN CONVENTION: " + str(signs))
        print("     A convention is a property of the design, not of a bucket, so this")
        print("     means at least one bucket's calibration is noise-driven. Pick the")
        print("     convention from the highest-attempt bucket, re-run with it forced,")
        print("     and do not ship a radar built on mixed conventions.")
    else:
        print(f"\n  sign convention consistent across buckets: {signs.pop()}")


if __name__ == "__main__":
    main()