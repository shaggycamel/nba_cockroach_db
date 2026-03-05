--CREATE OR REPLACE VIEW nba.nba_schedule_vw_new AS

SELECT 
	lgs.*
FROM nba.league_game_schedule AS lgs
INNER JOIN (SELECT team_slug FROM nba.teams) AS relevant_teams 
	ON lgs.team = relevant_teams.team_slug

	SELECT DISTINCT *
	FROM nba.league_game_schedule
WHERE game_id = 22500651

DROP VIEW nba.nba_schedule_vw_new
DROP VIEW nba.nba_player_box_score_vw_new

