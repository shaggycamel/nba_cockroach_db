CREATE OR REPLACE VIEW nba.nba_schedule_vw AS

SELECT 
	lgs.*
FROM nba.league_game_schedule AS lgs
INNER JOIN (SELECT team_slug FROM nba.teams) AS relevant_teams 
	ON lgs.team = relevant_teams.team_slug


