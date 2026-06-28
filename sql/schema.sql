-- Euroleague Play-Type RAPM — DuckDB schema (Week 1, reconciled Week 2)
-- Canonical store is Parquet; landing.pbp_lineups is a VIEW over the ingested
-- Parquet so new weekly games are reflected with no reload. Run via
-- scripts/build_warehouse.py (executes this file, then exports pbp_poss.parquet).
--
-- Column names mirror exactly what euroleague_api returns. Verified against
-- euroleague_api 0.1.1 (PlayByPlay.get_game_pbp_data_lineups + BoxScoreData).

------------------------------------------------------------------------------
-- 0. schemas
------------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS landing;    -- raw pulls, 1 row per source row
CREATE SCHEMA IF NOT EXISTS warehouse;  -- modelling-ready artifacts

------------------------------------------------------------------------------
-- 1. game schedule / metadata  (Schedule.get_gamecodes_season)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS landing.games (
    season        INTEGER NOT NULL,   -- start year, e.g. 2024 == 2024-25
    gamecode      INTEGER NOT NULL,   -- "gameCode" from schedule
    round         INTEGER,
    phase         VARCHAR,            -- "Phase" (RS / Playoffs / Final Four)
    date          DATE,
    home_team     VARCHAR,
    away_team     VARCHAR,
    home_score    INTEGER,
    away_score    INTEGER,
    played        BOOLEAN,
    PRIMARY KEY (season, gamecode)
);

------------------------------------------------------------------------------
-- 2. play-by-play enriched with on-court lineups  — VIEW over canonical Parquet
--    (PlayByPlay.get_game_pbp_data_lineups, validate=True)
--    Backed directly by data/pbp_lineups/**/*.parquet: no reload needed when the
--    weekly refresh adds games, and column drift can't cause an INSERT mismatch.
--    Columns (euroleague_api 0.1.1):
--      Season, Gamecode, PERIOD, MINUTE, MARKERTIME, TRUE_NUMBEROFPLAY,
--      NUMBEROFPLAY, CODETEAM, PLAYER_ID, PLAYER, PLAYTYPE, DORSAL, POINTS_A,
--      POINTS_B, COMMENT, PLAYINFO, IsHomeTeam, Lineup_A[], Lineup_B[],
--      validate_on_court_player. Order events by TRUE_NUMBEROFPLAY.
------------------------------------------------------------------------------
CREATE OR REPLACE VIEW landing.pbp_lineups AS
SELECT * FROM read_parquet('data/pbp_lineups/**/*.parquet');

------------------------------------------------------------------------------
-- 3. boxscore player stats (BoxScoreData.get_players_boxscore_stats)
--    Source of IsStarter, which seeds the lineup reconstruction.
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS landing.boxscore_players (
    "Season"     INTEGER NOT NULL,
    "Gamecode"   INTEGER NOT NULL,
    "Home"       INTEGER,        -- 1 home, 0 away
    "Team"       VARCHAR,
    "Player_ID"  VARCHAR,
    "Player"     VARCHAR,
    "IsStarter"  INTEGER,        -- 1 => part of starting five
    "Minutes"    VARCHAR,
    "Points"     INTEGER,
    "Plusminus"  DOUBLE,
    "Valuation"  INTEGER         -- PIR (box-score baseline in ch.7)
);

------------------------------------------------------------------------------
-- 4. Week-1 validation results (scripts/validate_lineups.py)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS landing.lineup_validation (
    season            INTEGER,
    gamecode          INTEGER,
    games_ok          BOOLEAN,
    boxscore_ok       BOOLEAN,
    n_actions         INTEGER,
    valid_rate        DOUBLE,
    five_invariant    DOUBLE,
    empty_lineup_rate DOUBLE,
    error             VARCHAR
);

------------------------------------------------------------------------------
-- 5. warehouse: possession-level stint matrix
--    NOTE (Wk2): the canonical Week-2 artifact is warehouse/stints.parquet,
--    written by build_stint_matrix.py with home/away orientation + lineup_ok.
--    This table's off/def orientation is a Week-3 design-matrix target; it is
--    realigned and populated when the RAPM design is fixed. Left as a forward
--    declaration for now (stays empty).
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.stints (
    season            INTEGER NOT NULL,
    gamecode          INTEGER NOT NULL,
    stint_id          INTEGER NOT NULL,   -- within game
    off_team          VARCHAR,
    def_team          VARCHAR,
    off_players       VARCHAR[],          -- 5 offensive player_ids
    def_players       VARCHAR[],          -- 5 defensive player_ids
    play_type         VARCHAR,            -- play-context tag (Week 2 tagger), NULL=unassigned
    possessions       INTEGER,
    points_scored     INTEGER,
    seconds           INTEGER,
    home_off          BOOLEAN,
    PRIMARY KEY (season, gamecode, stint_id)
);

-- modelling-clean actions: correctly-attributed individual actions only.
-- DISTINCTNESS (not len()=5) so duplicated-player fives from the sub-matcher
-- cascade are excluded — len()=5 passes a five with a repeated name.
CREATE OR REPLACE VIEW warehouse.pbp_clean AS
SELECT *
FROM landing.pbp_lineups
WHERE "validate_on_court_player" = TRUE
  AND len(list_distinct("Lineup_A")) = 5
  AND len(list_distinct("Lineup_B")) = 5;

-- possession-complete source: keep team/structural possession-enders (blank-PLAYER
-- team D/O/TO + BP/EP/TPOFF), drop ONLY the named mis-attributions. Reads landing.
-- Corrupt-five composition is handled at stint granularity in build_stint_matrix
-- (lineup_ok guard), NOT here, so the possession walker sees an unbroken stream.
CREATE OR REPLACE VIEW warehouse.pbp_poss AS
SELECT *
FROM landing.pbp_lineups
WHERE validate_on_court_player = TRUE       -- good named rows + IN/OUT subs
   OR NULLIF(TRIM(PLAYER_ID), '') IS NULL;  -- keep blank-player team D/O/TO + BP/EP/TPOFF