CREATE OR REPLACE VIEW nba.nba_team_roster_vw_new AS
SELECT 
  tr.season,
  tr.team_id,
  tr.team_slug,
  tr.player_id,
  nm.espn_id,
  nm.yahoo_id,
  nm.nba_name AS player_name,
  tr.position,
  tr.how_acquired,
  tr.salary,
  COALESCE(tr.entry_date, kd.begin_date) AS entry_date,
  COALESCE(tr.exit_date, kd.end_date) AS exit_date

FROM nba.team_roster AS tr
LEFT JOIN util.nba_fty_name_match AS nm ON tr.player_id = nm.nba_id
LEFT JOIN (SELECT * FROM nba.key_dates WHERE season_type = 'Regular Season') AS kd ON tr.season = kd.season