"""
build_stint_matrix.py  —  Week 2, O1
=====================================
Possession-level stint matrix for Euroleague RAPM, 2007-08 → 2025-26.

Consumes the *validated lineup PBP* (the same frame `warehouse.pbp_clean` is built
from: euroleague_api `PlayByPlay.get_game_pbp_data_lineups(validate=True)` output)
and emits one row per stint — a maximal span with both five-man lineups unchanged —
carrying offensive possessions and points for each team. This is the canonical
input to the Wk3 ridge design matrix.

INPUT CONTRACT  (one game per group; pass the full multi-season frame, it groups internally)
    Season              int
    Gamecode            int
    PERIOD              int        1..4 (+OT)
    TRUE_NUMBEROFPLAY   int        canonical event order (set by the wrapper)
    PLAYTYPE            str        event code (see CODES below)
    CODETEAM            str        team code of the acting team ('' for neutral rows)
    IsHomeTeam          bool|None
    Lineup_A            list[str]  home five (names) — forward-filled by the wrapper
    Lineup_B            list[str]  away five (names)
    validate_on_court_player  bool # rows == False already dropped by pbp_clean

OUTPUT  (parquet)  one row per stint:
    Season, Gamecode, stint_id,
    home_team, away_team,
    home_players (tuple[str]×5), away_players (tuple[str]×5),
    home_pts, away_pts, home_poss, away_poss, poss (=mean of the two), margin

────────────────────────────────────────────────────────────────────────────────
TWO THINGS TO CONFIRM AGAINST pbp_clean (I can't hit the live API from here):
  1. Exact PLAYTYPE strings for made FGs / FTs / rebounds / TOs (CODES below uses the
     standard Euroleague set; verify nothing in your warehouse differs, esp. LAYUPMD/DUNK).
  2. FT trip-end detection (`_is_trip_end`) is a look-ahead heuristic. RAPM is robust to
     small possession-count noise, but eyeball it on a couple of and-1 sequences.
────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import polars as pl

# ── Event-code config — verify against pbp_clean ────────────────────────────────
MADE_FG   = {"2FGM", "3FGM", "LAYUPMD", "DUNK"}
MADE_FT   = {"FTM"}
FT_ANY    = {"FTM", "FTA"}
DREB      = {"D"}          # defensive rebound — ends the *shooter's* possession
OREB      = {"O"}          # offensive rebound — possession continues
TURNOVER  = {"TO"}
END_PER   = {"EP"}
SUB_IN, SUB_OUT = "IN", "OUT"
NEUTRAL   = {"BP", "EP", "TPOFF", "JB", "TOUT", "TOUT_TV", "IN", "OUT", "C", "B"}
PTS = {"2FGM": 2, "3FGM": 3, "LAYUPMD": 2, "DUNK": 2, "FTM": 1}


def _is_trip_end(playtypes: list[str], i: int) -> bool:
    """A made FT ends the trip iff the next FT-relevant event is not another FT."""
    for j in range(i + 1, len(playtypes)):
        if playtypes[j] in FT_ANY:
            return False          # more FTs in this trip
        if playtypes[j] in OREB:  # missed-FT rebound path won't reach here (FTM made)
            return True
        return True
    return True


def _walk_game(g: pl.DataFrame) -> pl.DataFrame:
    """Possession + stint assignment for a single game (rows pre-sorted)."""
    g = g.sort("TRUE_NUMBEROFPLAY")
    pt     = g["PLAYTYPE"].to_list()
    team   = g["CODETEAM"].to_list()
    player = g["PLAYER"].to_list()
    la = g["Lineup_A"].to_list()
    lb = g["Lineup_B"].to_list()
    n = len(pt)

    # Home/away team codes by Lineup_A membership, NOT IsHomeTeam.
    # euroleague_api builds IsHomeTeam by comparing the stripped CODETEAM against
    # the UNstripped CodeTeamA, so for games whose feed pads team codes it is None
    # for every row. Lineup_A is the home five by construction, so the home team is
    # whichever team's actors appear in Lineup_A — robust to that wrapper bug.
    votes: dict[str, int] = {}
    for i in range(n):
        p, t, lineup = player[i], team[i], la[i]
        if p and t and lineup is not None and p in lineup:
            votes[t] = votes.get(t, 0) + 1
    htm = max(votes, key=votes.get) if votes else None
    teamset = {t for t in team if t}
    atm = next((t for t in teamset if t != htm), None)
    other = lambda t: atm if t == htm else htm

    poss_off  = [None] * n     # offensive team credited with the possession ending here
    poss_end  = [False] * n
    stint_id  = [0] * n

    off = None
    sid = 0
    prev_key = None

    for i in range(n):
        code, t = pt[i], team[i]
        # seed offensive team on first real offensive action
        if off is None and t and code not in NEUTRAL:
            off = t

        # stint boundary = either lineup changed since previous event
        key = (tuple(sorted(la[i])), tuple(sorted(lb[i])))
        if prev_key is not None and key != prev_key:
            sid += 1
        prev_key = key
        stint_id[i] = sid

        # possession-ending logic
        if code in MADE_FG:
            poss_end[i] = True; poss_off[i] = t; off = other(t)
        elif code in TURNOVER:
            poss_end[i] = True; poss_off[i] = t; off = other(t)
        elif code in DREB:
            shooter = other(t)                      # D credited to the defense
            poss_end[i] = True; poss_off[i] = shooter; off = t
        elif code in MADE_FT and _is_trip_end(pt, i):
            poss_end[i] = True; poss_off[i] = t; off = other(t)
        elif code in END_PER:
            poss_end[i] = True; poss_off[i] = off
            off = None                              # reset at period boundary
        # OREB and everything else: possession continues, no flip

    return g.with_columns(
        pl.Series("stint_id", stint_id),
        pl.Series("poss_end", poss_end),
        pl.Series("poss_off", poss_off, dtype=pl.Utf8),
        pl.lit(htm).alias("home_team"),
        pl.lit(atm).alias("away_team"),
    )


def _aggregate_stints(walked: pl.DataFrame) -> pl.DataFrame:
    """Collapse walked events → one row per (game, stint)."""
    rows = []
    skipped_games = set()
    for (season, game, sid), s in walked.group_by(
        ["Season", "Gamecode", "stint_id"], maintain_order=True
    ):
        htm, atm = s["home_team"][0], s["away_team"][0]
        if htm is None or atm is None:        # team codes unresolvable for this game
            skipped_games.add((season, game))
            continue
        # lineups are constant within a stint by construction → take first
        hp = tuple(sorted(s["Lineup_A"][0]))
        ap = tuple(sorted(s["Lineup_B"][0]))

        pts = s["PLAYTYPE"].replace_strict(PTS, default=0, return_dtype=pl.Int32)
        home_pts = int((pts * (s["CODETEAM"] == htm)).sum())
        away_pts = int((pts * (s["CODETEAM"] == atm)).sum())

        ends = s.filter(pl.col("poss_end"))
        home_poss = int((ends["poss_off"] == htm).sum())
        away_poss = int((ends["poss_off"] == atm).sum())

        rows.append({
            "Season": season, "Gamecode": game, "stint_id": sid,
            "home_team": htm, "away_team": atm,
            "home_players": hp, "away_players": ap,
            "home_pts": home_pts, "away_pts": away_pts,
            "home_poss": home_poss, "away_poss": away_poss,
            "poss": (home_poss + away_poss) / 2,
            "margin": home_pts - away_pts,
            # lineup-composition QC: a five with a duplicated name is 4 real
            # players + a phantom (substitution-matcher cascade). These are
            # invisible to validate_on_court_player and must not reach the
            # design matrix. See docs/wk1_validation.md.
            "lineup_ok": (len(set(hp)) == 5 and len(set(ap)) == 5),
        })
    if skipped_games:
        print(f"[QC] skipped {len(skipped_games)} game(s) with unresolvable home/away "
              f"team codes: {sorted(skipped_games)[:10]}"
              + (" …" if len(skipped_games) > 10 else ""))
    return pl.DataFrame(rows)


def build_stint_matrix(pbp: pl.DataFrame, drop_corrupt: bool = True) -> pl.DataFrame:
    """Full pipeline: validated lineup PBP (any #games) → stint table.

    drop_corrupt=True (default) removes stints whose home or away five has a
    duplicated player, and prints what was dropped. Set False to keep the
    `lineup_ok` flag and filter downstream yourself.
    """
    walked = pl.concat([
        _walk_game(g) for (_, _), g in
        pbp.group_by(["Season", "Gamecode"], maintain_order=True)
    ])
    stints = _aggregate_stints(walked)

    bad = stints.filter(~pl.col("lineup_ok"))
    if bad.height:
        games = bad["Gamecode"].n_unique()
        print(f"[QC] dropping {bad.height:,} corrupt-five stints across {games} "
              f"game(s) — duplicated-player lineups (sub-matcher cascade):")
        print(bad.group_by(["Season", "Gamecode"]).agg(pl.len().alias("stints"))
              .sort("stints", descending=True).head(10))
    return stints.filter(pl.col("lineup_ok")) if drop_corrupt else stints


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",  dest="src", required=True, help="validated lineup PBP parquet")
    ap.add_argument("--out", dest="dst", default="warehouse/stints.parquet")
    a = ap.parse_args()

    pbp = pl.read_parquet(a.src)
    stints = build_stint_matrix(pbp)
    stints.write_parquet(a.dst)

    n_games = stints.select(["Season", "Gamecode"]).unique().height
    poss = stints["poss"].sum()
    print(f"{stints.height:,} stints · {poss:,.0f} possessions · "
          f"{n_games:,} games · {stints['Season'].n_unique()} seasons → {a.dst}")
    # pace sanity — group by (Season, Gamecode); `poss` is per-team, so ×2 is total
    per_game = (stints.group_by(["Season", "Gamecode"])
                .agg(pl.col("poss").sum())["poss"].mean())
    print(f"poss/game ≈ {per_game:.1f}/team, {per_game*2:.1f} total  "
          f"(expect ~70-75 / ~140-150; off → check FT/code config)")