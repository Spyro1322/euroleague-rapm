# Week 1 — On-court lineup reconstruction: validation

**Result: the full 2007-08 → 2025-26 range is usable with no truncation. Individual-action
attribution is accurate to 99.88%; the on-court-check residual is dominated by team-credited
events that the modelling view removes.**

## Method
- `euroleague_api` 0.1.1, `PlayByPlay.get_game_pbp_data_lineups(validate=True)`.
- Stratified sample: 5 games/season × 19 seasons = **95 games, 48,827 PBP actions** (seed 42).
- Scripts: `scripts/validate_lineups.py` (structural), `scripts/breakdown_false_lineups.py`
  (residual decomposition with team-vs-named split).

## Structural integrity — all seasons
| signal | result |
|---|---|
| `five_invariant` | **1.000** every season — every action has two well-formed 5-man lineups |
| `empty_lineup_rate` | **0.000** — boxscore starters recovered for every sampled game |
| `valid_rate` | flat **0.939–0.965**, no early-season cliff (oldest seasons marginally cleanest) |

The silent failure mode (missing `IsStarter` → empty lineups in old seasons) did **not** occur.

## Residual decomposition — `validate_on_court_player == False`
- 4.76% of all actions flagged; 64.9% non-player structural rows, 32.5% player-action codes.
- Of **36,931** individual-action rows, **730 (94.3% of player-action False)** are team-credited
  events (team rebounds `D`/`O`, team turnovers `TO`) with blank `PLAYER_ID` — benign, dropped
  by `warehouse.pbp_clean`.
- **Named mis-attribution: 44 rows = 0.119%** of individual actions (~1 in 840).
  - Field goals + free throws: 3 / ~14,900 → **99.98%** accurate.
  - Assists: 11 / 3,185 → 99.65%.
  - Steals: 14 / 1,355 → 98.97% (largest single contributor; defender's steal recorded across a
    substitution beat).
- 13 rows of unknown codes `C`/`B` (0.027%) left flagged; immaterial.

## Decisions
1. **Usable season range: full 2007-08 → 2025-26, no truncation.**
2. **No possession-level sub-timing correction applied** — residual magnitude (0.12%) does not
   justify it; flagged rows excluded via `warehouse.pbp_clean`.

## Thesis sentences (paste-ready)
**Ch. 3 (Data & ETL, validation):** On-court reconstruction was validated on a stratified sample
of 95 games (five per season, 2007-08 to 2025-26; 48,827 actions). Every action across all seasons
yielded two well-formed five-man lineups (`five_invariant` = 1.000) with starters recovered for
every game. Of 36,931 individual-action rows, only 0.12% attributed an action to a lineup not
containing the named actor; the remaining on-court-check failures were team-credited events (team
rebounds, team turnovers, timeouts) carrying no individual and are removed by the modelling view.
Field-goal, free-throw and assist attribution exceeded 99.6%.

**Ch. 9 (Limitations):** The reconstruction carries a residual individual mis-attribution rate of
≈0.12%, concentrated in steals and offensive rebounds recorded near substitutions. Given its
magnitude (≈1 action in 840), no possession-level correction was applied and flagged rows are
excluded via the clean view.
