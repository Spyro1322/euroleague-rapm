-- Euroleague Play-Type RAPM — DuckDB schema (Week 1)
-- Canonical store is Parquet; these tables are DuckDB views/tables over the
-- landing + warehouse parquet artifacts. Run: duckdb warehouse.duckdb < sql/schema.sql
--
-- Column names mirror exactly what euroleague_api returns so ingestion is a
-- straight write with no renaming surprises. Verified against euroleague_api
-- 0.1.1 (PlayByPlay.get_game_pbp_data_lineups + BoxScoreData).

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
-- 2. play-by-play enriched with on-court lineups
--    (PlayByPlay.get_game_pbp_data_lineups, validate=True)
--    Lineup_A/Lineup_B are 5-element player lists -> stored as VARCHAR[].
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS landing.pbp_lineups (
    "Season"                   INTEGER NOT NULL,
    "Gamecode"                 INTEGER NOT NULL,
    "PERIOD"                   INTEGER,        -- 1-4 reg, 5 = OT
    "MINUTE"                   INTEGER,
    "MARKERTIME"               VARCHAR,        -- mm:ss on game clock
    "TRUE_NUMBEROFPLAY"        INTEGER,        -- monotonic event order (use this)
    "NUMBEROFPLAY"             INTEGER,        -- raw, often out of order
    "CODETEAM"                 VARCHAR,        -- acting team code
    "PLAYER_ID"                VARCHAR,
    "PLAYER"                   VARCHAR,
    "PLAYTYPE"                 VARCHAR,        -- 2FGM, AST, IN, OUT, TO, ...
    "DORSAL"                   VARCHAR,
    "POINTS_A"                 INTEGER,
    "POINTS_B"                 INTEGER,
    "COMMENT"                  VARCHAR,
    "PLAYINFO"                 VARCHAR,
    "IsHomeTeam"               BOOLEAN,
    "Lineup_A"                 VARCHAR[],      -- home five at this action
    "Lineup_B"                 VARCHAR[],      -- away five at this action
    "validate_on_court_player" BOOLEAN,        -- data-quality flag (see ETL notes)
    PRIMARY KEY ("Season", "Gamecode", "TRUE_NUMBEROFPLAY")
);

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
-- 5. warehouse: possession-level stint matrix  (Week 2 — schema defined now)
--    One row per uninterrupted stint (same 10 players, same offence/defence).
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.stints (
    season            INTEGER NOT NULL,
    gamecode          INTEGER NOT NULL,
    stint_id          INTEGER NOT NULL,   -- within game
    off_team          VARCHAR,
    def_team          VARCHAR,
    off_players       VARCHAR[],          -- 5 offensive player_ids
    def_players       VARCHAR[],          -- 5 defensive player_ids
    play_type         VARCHAR,            -- 7-type tag (Week 2 tagger), NULL=unassigned
    possessions       INTEGER,
    points_scored     INTEGER,
    seconds           INTEGER,
    home_off          BOOLEAN,
    PRIMARY KEY (season, gamecode, stint_id)
);

-- convenience: only modelling-clean actions (drop flagged on-court mismatches)
CREATE OR REPLACE VIEW warehouse.pbp_clean AS
SELECT *
FROM landing.pbp_lineups
WHERE "validate_on_court_player" = TRUE
  AND len("Lineup_A") = 5
  AND len("Lineup_B") = 5;
