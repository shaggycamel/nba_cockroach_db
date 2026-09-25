CREATE OR REPLACE VIEW fty.fty_free_agents_vw AS

SELECT 
	fa.season,
	fa.platform,
	fa.league_id,
	nm.player_id,
	fa.player_id AS fantasy_id,
	nm.player_name,
	fa.player_team
	
FROM fty.free_agents AS fa

LEFT JOIN (

	SELECT 
		'ESPN' AS platform,
		espn_id AS fantasy_id,
		nba_id AS player_id,
		conformed_name AS player_name
	FROM util.conformed_player_id
	
	UNION ALL
	
	SELECT 
		'Yahoo' AS platform,
		yahoo_id AS fantasy_id,
		nba_id AS player_id,
		conformed_name AS player_name
	FROM util.conformed_player_id
	
) AS nm ON fa.platform = nm.platform
	AND fa.player_id = nm.fantasy_id