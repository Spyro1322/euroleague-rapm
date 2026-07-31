"""
scripts/inspect_landing.py

Inventories the raw shot ingest in landing/ and answers, precisely:

  1. Where is landing/, and how is it laid out?
  2. Which seasons ingested cleanly (_SUCCESS) and which have gaps (_MISSING.csv)?
  3. Do the raw shards carry every column the tagger needs?
  4. How many seasons/rows does the re-tag job actually cover?
     (i.e. landing seasons MINUS seasons already in tagged_shots_ids)
  5. Do the Week 5 coverage claims hold on the raw data?
       - pct_coords 0.97-0.99 across all 19 seasons
       - FASTBREAK / SECOND_CHANCE cliff at 2015-16 (~0 pre-2015, 0.76 in 2015, 1.0 from 2016)
     These are re-verified here because the O3 bucket-availability decision rests
     on them and they were measured by a report that later needed a schema fix.

Read-only. Writes nothing.

Usage:
    python3 scripts/inspect_landing.py
    python3 scripts/inspect_landing.py --landing ../landing
    python3 scripts/inspect_landing.py --landing /abs/path/to/landing --deep
      --deep also reports per-season shot-type mix, which is slower.
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

# Columns the shot-context tagger needs. Missing any of these in a season's
# shards means that season cannot be tagged, regardless of _SUCCESS.
TAGGER_REQUIRED = [
    "Season", "Gamecode", "NUM_ANOT", "TEAM", "PLAYER", "ID_ACTION",
    "COORD_X", "COORD_Y", "FASTBREAK", "SECOND_CHANCE",
]

CANDIDATE_LANDINGS = [
    "landing", "../landing", "../../landing",
    "~/landing", "./data/landing", "../data/landing",
]

SEASON_RE = re.compile(r"(?:^|[^0-9])(20(?:0[7-9]|1[0-9]|2[0-5]))(?:[^0-9]|$)")


def find_landing(explicit):
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise SystemExit(f"--landing {p} does not exist")
        return p
    for c in CANDIDATE_LANDINGS:
        p = Path(c).expanduser().resolve()
        if p.exists() and p.is_dir():
            if list(p.rglob("*.parquet")):
                return p
    raise SystemExit(
        "Could not locate landing/. Pass it explicitly: --landing /path/to/landing"
    )


def season_from_path(path: Path, root: Path):
    """Infer season from any path component between root and the file."""
    rel = path.relative_to(root)
    for part in list(rel.parts)[::-1]:
        m = SEASON_RE.search(part)
        if m:
            return int(m.group(1))
    return None


def hr(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", default=None)
    ap.add_argument("--warehouse", default="warehouse")
    ap.add_argument("--deep", action="store_true")
    args = ap.parse_args()

    root = find_landing(args.landing)
    W = Path(args.warehouse)

    # ------------------------------------------------------------ 1. layout
    hr(f"1. LAYOUT  —  landing root = {root}")
    all_pq = sorted(root.rglob("*.parquet"))
    print(f"  parquet shards found: {len(all_pq):,}")
    if not all_pq:
        raise SystemExit("  no parquet under landing/ — wrong path?")

    # top-level structure, 2 levels deep
    tops = defaultdict(int)
    for p in all_pq:
        rel = p.relative_to(root)
        key = "/".join(rel.parts[:2]) if len(rel.parts) > 2 else "/".join(rel.parts[:-1])
        tops[key or "."] += 1
    print("  shard distribution (first two path levels):")
    for k in sorted(tops):
        print(f"    {k or '.'}/  ->  {tops[k]:,} shard(s)")

    print("\n  example shard paths:")
    for p in all_pq[:3]:
        print(f"    {p.relative_to(root)}")
    if len(all_pq) > 3:
        print(f"    ... and {len(all_pq)-3:,} more")

    # group shards by inferred season
    by_season = defaultdict(list)
    unknown = []
    for p in all_pq:
        s = season_from_path(p, root)
        (by_season[s] if s else unknown).append(p)
    print(f"\n  seasons inferred from path: {sorted(by_season)}")
    if unknown:
        print(f"  shards with NO season in path: {len(unknown):,} "
              f"(will read Season column from data below)")
        # recover season from data for these
        rec = defaultdict(list)
        for p in unknown:
            try:
                t = pq.read_table(p, columns=["Season"])
                for s in set(t.column("Season").to_pylist()):
                    rec[int(s)].append(p)
            except Exception as e:
                print(f"    !! {p.name}: {e}")
        for s, ps in rec.items():
            by_season[s].extend(ps)
        print(f"  seasons after reading data: {sorted(by_season)}")

    # ------------------------------------------- 2. completeness markers
    hr("2. COMPLETENESS MARKERS  (_SUCCESS / _MISSING.csv per season)")
    succ = list(root.rglob("_SUCCESS"))
    miss = list(root.rglob("_MISSING.csv"))
    print(f"  _SUCCESS markers: {len(succ)}")
    print(f"  _MISSING.csv files: {len(miss)}")

    succ_seasons = {season_from_path(p, root) for p in succ} - {None}
    miss_seasons = {season_from_path(p, root) for p in miss} - {None}
    print(f"  seasons with _SUCCESS: {sorted(succ_seasons)}")
    print(f"  seasons with _MISSING: {sorted(miss_seasons)}")

    if miss:
        print("\n  _MISSING.csv contents:")
        for p in sorted(miss):
            try:
                m = pl.read_csv(p)
                print(f"    {p.relative_to(root)}: {m.height} row(s)")
                if m.height:
                    print(m.head(5))
            except Exception as e:
                print(f"    {p.relative_to(root)}: unreadable ({e})")

    expected = set(range(2007, 2026))
    print(f"\n  seasons with shards but NO _SUCCESS: "
          f"{sorted(set(by_season) - succ_seasons)}")
    print(f"  expected seasons with no shards at all: "
          f"{sorted(expected - set(by_season))}")

    # ------------------------------------------- 3. tagger input schema
    hr("3. TAGGER INPUT SCHEMA  (are the required columns present, per season?)")
    print(f"  required: {TAGGER_REQUIRED}")
    schema_by_season = {}
    for s in sorted(by_season):
        p = by_season[s][0]
        try:
            sch = pq.read_schema(p)
            names = set(sch.names)
        except Exception as e:
            print(f"  {s}: !! unreadable ({e})")
            continue
        schema_by_season[s] = names
        missing = [c for c in TAGGER_REQUIRED if c not in names]
        flag = "OK" if not missing else f"MISSING {missing}"
        print(f"  {s}: {len(names):3d} cols  shards={len(by_season[s]):4d}  {flag}")

    if schema_by_season:
        first = sorted(schema_by_season)[0]
        print(f"\n  full column list ({first}):")
        p = by_season[first][0]
        for f in pq.read_schema(p):
            print(f"    {f.name:28s} {f.type}")
        # schema drift across seasons
        base = schema_by_season[first]
        drift = {s: (sorted(base - n), sorted(n - base))
                 for s, n in schema_by_season.items() if n != base}
        if drift:
            print(f"\n  SCHEMA DRIFT vs {first}:")
            for s, (gone, extra) in sorted(drift.items()):
                print(f"    {s}: absent={gone} extra={extra}")
        else:
            print("\n  schema identical across all seasons.")

    # ------------------------------------------- 4. re-tag scope
    hr("4. RE-TAG SCOPE  (landing seasons vs already-tagged seasons)")
    rows_by_season = {}
    for s in sorted(by_season):
        n = 0
        for p in by_season[s]:
            try:
                n += pq.read_metadata(p).num_rows
            except Exception:
                pass
        rows_by_season[s] = n

    tagged_seasons = set()
    tp = W / "tagged_shots_ids.parquet"
    if tp.exists():
        tagged = pl.read_parquet(tp, columns=["Season"])
        tagged_seasons = set(tagged["Season"].unique().to_list())
        print(f"  tagged_shots_ids covers: {sorted(tagged_seasons)} "
              f"({tagged.height:,} rows)")
    else:
        print("  tagged_shots_ids.parquet not found — everything needs tagging")

    todo = sorted(set(by_season) - tagged_seasons)
    todo_rows = sum(rows_by_season.get(s, 0) for s in todo)
    total_rows = sum(rows_by_season.values())

    print(f"\n  {'season':>8} {'shards':>8} {'raw rows':>12}   status")
    for s in sorted(by_season):
        st = "tagged" if s in tagged_seasons else "NEEDS TAGGING"
        print(f"  {s:>8} {len(by_season[s]):>8} {rows_by_season[s]:>12,}   {st}")
    print(f"\n  raw rows total:        {total_rows:>12,}")
    print(f"  raw rows to tag:       {todo_rows:>12,}  across {len(todo)} season(s)")
    print(f"  seasons needing tag:   {todo}")

    # ------------------------------------------- 5. coverage re-verification
    hr("5. COVERAGE RE-VERIFICATION  (does the O3 decision still hold?)")
    print("  Week 5 claims under test:")
    print("    (a) pct_coords 0.97-0.99 for ALL 19 seasons")
    print("    (b) FASTBREAK/SECOND_CHANCE ~0 pre-2015, ~0.76 in 2015, ~1.0 from 2016")
    print()
    print("  PRESENT vs TRUE — these are different questions and the O3 decision")
    print("  depends on the first, not the second:")
    print("    present = the feed carries a value at all (either 0 or 1).")
    print("              This is what the Week 5 'rate' numbers meant. A season")
    print("              with present~0 has NO information on that flag.")
    print("    true    = the value is 1, i.e. the shot really was a fastbreak /")
    print("              second-chance. This is a basketball rate (~5-12%), and it")
    print("              should be roughly flat across the flag-complete era.")
    print("  A season where present is high but true is 0 would mean the flag is")
    print("  carried but never set — a silent defect the Week 5 report could not")
    print("  have distinguished from a genuinely low fastbreak rate.")
    print(f"\n  {'season':>8} {'rows':>10} {'coords':>8} "
          f"{'fb_pres':>8} {'fb_true':>8} {'sc_pres':>8} {'sc_true':>8}")

    ABSENT = ["", "-", "None", "none", "null", "NULL", "nan", "NaN"]
    TRUTHY = ["1", "1.0", "True", "true", "TRUE", "Y", "y"]

    def present_rate(col: pl.Series) -> float:
        """Flag carried at all — '0' COUNTS AS PRESENT. This is availability."""
        s = col.cast(pl.Utf8).fill_null("").str.strip_chars()
        return float((~s.is_in(ABSENT)).mean())

    def true_rate(col: pl.Series) -> float:
        """Flag set to 1. This is the basketball rate, not availability."""
        s = col.cast(pl.Utf8).fill_null("").str.strip_chars()
        return float(s.is_in(TRUTHY).mean())

    results = []
    for s in sorted(by_season):
        names = schema_by_season.get(s, set())
        want = [c for c in ("COORD_X", "COORD_Y", "FASTBREAK", "SECOND_CHANCE") if c in names]
        frames = []
        for p in by_season[s]:
            try:
                frames.append(pl.read_parquet(p, columns=want))
            except Exception:
                pass
        if not frames:
            print(f"  {s:>8} {'-':>10} {'unreadable':>11}")
            continue
        df = pl.concat(frames, how="diagonal_relaxed")
        n = df.height
        if {"COORD_X", "COORD_Y"}.issubset(df.columns):
            coords = float(
                (df["COORD_X"].is_not_null() & df["COORD_Y"].is_not_null()
                 & ~((df["COORD_X"] == 0) & (df["COORD_Y"] == 0))).mean()
            )
        else:
            coords = float("nan")
        nan = float("nan")
        fbp = present_rate(df["FASTBREAK"]) if "FASTBREAK" in df.columns else nan
        fbt = true_rate(df["FASTBREAK"]) if "FASTBREAK" in df.columns else nan
        scp = present_rate(df["SECOND_CHANCE"]) if "SECOND_CHANCE" in df.columns else nan
        sct = true_rate(df["SECOND_CHANCE"]) if "SECOND_CHANCE" in df.columns else nan
        results.append((s, n, coords, fbp, fbt, scp, sct))
        print(f"  {s:>8} {n:>10,} {coords:>8.3f} "
              f"{fbp:>8.3f} {fbt:>8.3f} {scp:>8.3f} {sct:>8.3f}")

    if results:
        low = [(s, round(c, 3)) for s, _, c, _, _, _, _ in results if c == c and c < 0.95]
        print("\n  (a) coordinate claim: "
              + ("HOLDS — every season >= 0.95" if not low
                 else f"FAILS for {low} — those seasons cannot use location buckets"))

        # Re-derive the boundary from PRESENCE rather than assuming 2016.
        FLAG_PRESENT_MIN = 0.90
        usable = sorted(s for s, _, _, fbp, _, scp, _ in results
                        if fbp == fbp and scp == scp
                        and fbp >= FLAG_PRESENT_MIN and scp >= FLAG_PRESENT_MIN)
        print(f"\n  (b) flag availability, derived from presence (>= {FLAG_PRESENT_MIN}):")
        if usable:
            # contiguous run check — a gap in the middle would break the "cliff" story
            contiguous = usable == list(range(usable[0], usable[-1] + 1))
            print(f"      flag-complete seasons: {usable}")
            print(f"      contiguous run? {contiguous}")
            print(f"      >>> DERIVED BOUNDARY: first flag-complete season = {usable[0]}")
            if usable[0] != 2016:
                print(f"      >>> MISMATCH: the O3 decision and the design-matrix mask")
                print(f"          both hardcode 2016. This table says {usable[0]}.")
                print(f"          Change FLAG_BUCKET_MIN_SEASON to {usable[0]} and restate")
                print(f"          the boundary in Ch5 before building any design.")
            else:
                print("      >>> matches the 2016 boundary already recorded. No change needed.")
            if not contiguous:
                gaps = sorted(set(range(usable[0], usable[-1] + 1)) - set(usable))
                print(f"      >>> NON-CONTIGUOUS: seasons {gaps} sit inside the supposed")
                print(f"          flag-complete era but are not flag-complete. The masking")
                print(f"          rule cannot be a single cutoff year — it must be a")
                print(f"          per-season set. Fix before building the design.")
        else:
            print("      NO season reaches the presence threshold — the two situation")
            print("      buckets are not estimable anywhere. O3 drops to 4 buckets.")

        partial = [(s, round(fbp, 3), round(scp, 3)) for s, _, _, fbp, _, scp, _ in results
                   if fbp == fbp and 0.10 < fbp < FLAG_PRESENT_MIN]
        if partial:
            print(f"      partial-coverage seasons (transition years): {partial}")
            print("      >>> These are neither usable nor cleanly absent. Excluding them")
            print("          from the two situation buckets is the conservative call.")

        # carried-but-never-set: presence high, truth zero => silent defect
        dead = [(s, round(fbp, 3), round(fbt, 3), round(scp, 3), round(sct, 3))
                for s, _, _, fbp, fbt, scp, sct in results
                if (fbp == fbp and fbp >= FLAG_PRESENT_MIN and fbt == fbt and fbt < 0.005)
                or (scp == scp and scp >= FLAG_PRESENT_MIN and sct == sct and sct < 0.005)]
        print("\n  (c) carried-but-never-set check:")
        if dead:
            print(f"      >>> SILENT DEFECT in {dead}")
            print("          (season, fb_present, fb_true, sc_present, sc_true)")
            print("          The flag column exists and is populated, but is never 1.")
            print("          Those seasons would contribute ONLY negative evidence to the")
            print("          situation buckets and must be excluded like the pre-2015 era.")
            print("          The Week 5 report could not have caught this.")
        else:
            print("      clean — every flag-complete season also has a nonzero true rate.")

        rates = [(s, round(fbt, 3), round(sct, 3)) for s, _, _, fbp, fbt, scp, sct in results
                 if fbp == fbp and fbp >= FLAG_PRESENT_MIN]
        if rates:
            fbs = [f for _, f, _ in rates]
            scs = [c for _, _, c in rates]
            print(f"\n  (d) true-rate stability across flag-complete seasons:")
            print(f"      fastbreak    min={min(fbs):.3f} max={max(fbs):.3f} spread={max(fbs)-min(fbs):.3f}")
            print(f"      second-chance min={min(scs):.3f} max={max(scs):.3f} spread={max(scs)-min(scs):.3f}")
            print("      >>> A large spread here is a tagger/feed consistency problem, not")
            print("          a basketball trend. Investigate before pooling these seasons.")

    if args.deep and "ID_ACTION" in TAGGER_REQUIRED:
        hr("6. DEEP — shot-type mix per season (sanity on ID_ACTION vocabulary)")
        for s in sorted(by_season):
            frames = []
            for p in by_season[s]:
                try:
                    frames.append(pl.read_parquet(p, columns=["ID_ACTION"]))
                except Exception:
                    pass
            if not frames:
                continue
            df = pl.concat(frames, how="diagonal_relaxed")
            vc = df.group_by("ID_ACTION").agg(pl.len().alias("n")).sort("n", descending=True)
            print(f"\n  {s}: {vc.height} distinct action codes")
            print(vc.head(8))

    print("\n" + "=" * 74)
    print("Paste this output back, together with diagnose_wk6_round2.py's.")
    print("=" * 74)


if __name__ == "__main__":
    main()
