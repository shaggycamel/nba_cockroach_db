CREATE OR REPLACE VIEW nba.nba_season_segments_vw AS

SELECT key_dates.season,
    key_dates.season_type,
    key_dates.begin_date,
    key_dates.end_date,
    ("right"(key_dates.season, 2) || ' - '::text) || key_dates.season_type AS year_season_type
   FROM nba.key_dates
  WHERE key_dates.season_type <> 'All Star'::text;
