#!/usr/bin/env bash
# scripts/refresh_dashboard.sh — operator-triggered weekly refresh (O5)
#
# WHY THIS IS NOT A GITHUB ACTIONS CRON
# A scheduled CI job cannot rebuild this pipeline. The raw inputs it needs are
# gitignored and too large to carry in version control:
#     data/shots/          5,039 shards
#     data/pbp_lineups/    play-by-play source
#     warehouse/           ~260 MB including a 34 MB pbp_poss.parquet
# A CI runner checks out a repo without them, so build_stint_matrix.py and
# tag_shots.py have nothing to read. The previous refresh.yml went straight to
# build_rapm_design.py, which reads artifacts already in warehouse/ — so on a
# runner it failed outright, and locally it would have refit identical data,
# produced a byte-identical parquet, hit `git diff --cached --quiet`, printed
# "No changes to commit" and exited GREEN having changed nothing.
#
# A weekly job that silently refreshes nothing is worse than one that fails.
# This script runs the same chain on the machine that holds the data, verifies
# the output, and pushes to the deployment mirror — which is what Community
# Cloud watches, so the live app redeploys exactly as it would have.
#
# O5 is unaffected: public dashboard, pre-computed artifacts, refreshed on a
# weekly cadence. Only the trigger is an operator rather than cron. Documented
# in Ch8 §8.7.
#
# Usage:
#     bash scripts/refresh_dashboard.sh            # full: ingest -> push
#     bash scripts/refresh_dashboard.sh --no-ingest   # skip the API pull
#     bash scripts/refresh_dashboard.sh --dry-run     # rebuild, do not push
set -euo pipefail

SEASON="${SEASON:-2025}"
# CONFIRM: what build_stint_matrix.py --in expects. Its help says "validated
# lineup PBP parquet". Candidates are warehouse/pbp_poss.parquet (if
# build_warehouse.py produces it) or a glob over data/pbp_lineups/. Set this
# before the first real run.
PBP_SRC="${PBP_SRC:-warehouse/pbp_poss.parquet}"
# The deployed rapm_dash.parquet was produced by (shell history, Week 4):
#     fit_ridge_rapm.py --prefix rapm_dash --bootstrap 500 --out rapm_dash
# i.e. DEFAULT --min-poss and --min-games, and NO --alpha (CV selected 3162.3).
# Do not pass the floors explicitly here: overriding them with values that
# differ from the defaults would change who qualifies for the leaderboard,
# which is a change to the published result rather than a data update.
DASH_ALPHA="${DASH_ALPHA:-3162.3}"
SHOTCTX_ALPHA="${SHOTCTX_ALPHA:-3162}"
MIRROR="${MIRROR:-../euroleague-rapm-dashboard}"

INGEST=1; PUSH=1; FULL=0
for a in "$@"; do
  case "$a" in
    --no-ingest) INGEST=0 ;;
    --dry-run)   PUSH=0 ;;
    --full)      FULL=1 ;;   # re-tag all 19 seasons instead of just $SEASON
    *) echo "unknown flag: $a"; exit 2 ;;
  esac
done

_t0=$(date +%s)
log() {
  local now; now=$(date +%s)
  printf '\n\033[1m== %s\033[0m  \033[2m[+%ds]\033[0m\n' "$1" "$((now-_t0))"
}
[ -d warehouse ] || { echo "run from the main repo root"; exit 1; }

if [ "$INGEST" = 1 ]; then
  log "1/5  ingest season $SEASON"
  # NOTE: ingest_shots.py enforces REQUEST_DELAY_S=1.5 between calls; a full
  # season takes a while. The season-level completeness gate writes _SUCCESS
  # per season and _MISSING.csv on partial failure — check both afterwards.
  # NOTE: three different season-range conventions in one pipeline --
  #   ingest_pbp / ingest_shots : --seasons 2007-2025   (hyphen)
  #   ingest_boxscore           : --start 2007 --end 2025
  #   build_rapm_design         : --seasons 2007:2025   (colon)
  # Getting one wrong fails at runtime, not at review. Worth a Ch9 note.
  python3 scripts/ingest_pbp.py      --seasons "$SEASON"
  python3 scripts/ingest_boxscore.py --start "$SEASON" --end "$SEASON"
  python3 scripts/ingest_shots.py    --seasons "$SEASON"
else
  log "1/5  ingest SKIPPED (--no-ingest)"
fi

log "2/5  stints, shot tagging, player ids"
# build_warehouse.py may need to run first to refresh $PBP_SRC from the newly
# ingested data/pbp_lineups shards -- CONFIRM and uncomment if so.
# python3 scripts/build_warehouse.py

python3 scripts/build_stint_matrix.py --in "$PBP_SRC"
log "    stints done"

# ---- INCREMENTAL TAGGING --------------------------------------------------
# Seasons 2007..(SEASON-1) are finished and never change. Re-tagging all 19 every
# week means reading 5,039 shards and running a row-wise classifier over 755k
# rows to pick up perhaps forty new ones. Tag only the current season and splice
# it into the existing file.
#
# This is safe because tag_shots.py is deterministic and stateless: the same
# shard yields the same rows regardless of what else is in the glob. The splice
# replaces the whole current season rather than appending, so re-running mid-week
# is idempotent.
#
# Use --full after ANY change to play_context.py, tag_shots.py, or the location
# rules -- otherwise old seasons keep labels from the previous logic and the
# taxonomy silently becomes inconsistent across the range.
TAGGED="warehouse/tagged_shots.parquet"
if [ "$FULL" = 1 ] || [ ! -f "$TAGGED" ]; then
  echo "    full-range tagging (all seasons)"
  python3 scripts/tag_shots.py
else
  echo "    incremental tagging (season $SEASON only; --full to re-tag all)"
  python3 scripts/tag_shots.py \
      --shots "data/shots/season=$SEASON/*.parquet" \
      --out "warehouse/tagged_shots_$SEASON.parquet"
  python3 - "$SEASON" <<'PY'
import sys, polars as pl
season = int(sys.argv[1])
old = pl.read_parquet("warehouse/tagged_shots.parquet")
new = pl.read_parquet(f"warehouse/tagged_shots_{season}.parquet")
kept = old.filter(pl.col("Season") != season)
out = pl.concat([kept, new], how="diagonal_relaxed").sort(["Season", "Gamecode", "NUM_ANOT"])
seasons = sorted(out["Season"].unique().to_list())
if len(seasons) < 19:
    sys.exit(f"FAIL: spliced file covers {len(seasons)} seasons, expected 19. "
             f"Missing {[s for s in range(2007, 2026) if s not in seasons]}. "
             f"Run with --full.")
out.write_parquet("warehouse/tagged_shots.parquet")
print(f"    spliced: {kept.height:,} historical + {new.height:,} season-{season} "
      f"= {out.height:,} rows across {len(seasons)} seasons")
PY
fi
log "    tagging done"

python3 scripts/build_player_id_map.py  # no args
log "    id map done"

log "3/5  overall RAPM (Tab 1)"
# alpha pinned: an unattended refit must not re-select a hyperparameter, or the
# deployed model drifts from the one documented in Ch4 with no record of when.
python3 scripts/build_rapm_design.py --seasons 2021:2025 --prefix rapm_dash
# --out takes a STEM, not a path: the script writes warehouse/<stem>.parquet.
# --alpha is the one deliberate divergence from the Week 4 command, which had no
# --alpha and let CV choose (it chose 3162.3). Pinning reproduces that value and
# stops an unattended refit re-selecting a neighbouring point on a very flat CV
# curve. VERIFY THE FIRST PINNED RUN against the deployed leaderboard.
python3 scripts/fit_ridge_rapm.py --prefix rapm_dash \
    --alpha "$DASH_ALPHA" --bootstrap 500 --out rapm_dash

log "4/5  shot-context RAPM (Tab 2)"
# --force-signs is mandatory. Per-bucket sign calibration is noise-driven on the
# thin buckets and got the convention backwards on corner_three in Week 6.
# Getting it wrong inverts every defensive spoke while the chart still looks
# entirely plausible.
python3 scripts/build_shotctx_design.py --window dash
python3 scripts/fit_shotctx_rapm.py --window dash \
    --alpha "$SHOTCTX_ALPHA" --force-signs +1,-1
python3 scripts/assess_identifiability.py --windows dash
python3 scripts/export_shotctx_parquet.py --window dash

log "5/5  verify"
python3 - <<'PY'
import sys, polars as pl
d = pl.read_parquet("warehouse/shotctx_dash.parquet")
need = {"player_id","name","bucket","end","value","prior","deviation",
        "support","reliable","signal","verdict","league_mean","alpha"}
missing = need - set(d.columns)
if missing:
    sys.exit(f"FAIL: shotctx_dash.parquet missing columns {sorted(missing)}")
if d.height == 0:
    sys.exit("FAIL: empty artifact")
v = dict(d.select(["bucket","verdict"]).unique().iter_rows())
print("  verdicts:", v)
if v.get("at_rim") != "STRONG" or v.get("mid_range") != "STRONG":
    sys.exit("FAIL: at_rim / mid_range no longer STRONG. The model has changed "
             "materially since Week 6 — investigate before this goes live.")
lb = pl.read_parquet("warehouse/rapm_dash.parquet")
print(f"  rapm_dash: {lb.height:,} players")
# A refresh should add games, not change who qualifies. A large swing in the
# player count means the possession/game floors differ from the deployed fit.
if not (450 <= lb.height <= 620):
    sys.exit(f"FAIL: rapm_dash has {lb.height} players; the deployed fit has 517. "
             "The qualification floors have changed. Do not publish -- compare the "
             "invocation against the Week 4 command in the header of this script.")
print(f"  shotctx_dash: {d.height:,} rows, {d['player_id'].n_unique():,} players")
PY

if [ "$PUSH" = 0 ]; then
  log "dry run — artifacts rebuilt, nothing pushed"
  exit 0
fi

[ -d "$MIRROR/app/warehouse" ] || { echo "mirror not found at $MIRROR"; exit 1; }

log "push to deployment mirror"
cp warehouse/rapm_dash.parquet    "$MIRROR/app/warehouse/"
cp warehouse/shotctx_dash.parquet "$MIRROR/app/warehouse/"
cd "$MIRROR"
# Both artifacts in ONE commit, always. If Tab 1 refreshes and Tab 2 does not,
# the two tabs silently display different weeks and nothing errors.
git add app/warehouse/rapm_dash.parquet app/warehouse/shotctx_dash.parquet
if git diff --cached --quiet; then
  echo "  no changes — artifacts identical to the deployed version"
  echo "  (if this repeats week after week, the ingest is not picking up new games)"
else
  git commit -m "chore: weekly refresh $(date -u +%F)"
  git push
  echo "  pushed — Community Cloud will redeploy within a minute or two"
fi