CREATE OR REPLACE VIEW nba.nba_teams_vw AS

SELECT 
	team_id,
	team_slug,
	team_long,
	team_name
FROM nba.teams
WHERE active