CREATE OR REPLACE VIEW fty.fty_recent_activity_vw AS
SELECT 
	activity.season,
	activity.platform,
	activity.league_id,
	lgl.league_name,
	activity.competitor_id,
	lc.competitor_name,
	activity.player,
	activity.action,
	activity.timestamp
FROM fty.recent_activity AS activity

LEFT JOIN fty.league as lgl ON activity.season = lgl.season
	AND activity.platform = lgl.platform
	AND activity.league_id = lgl.league_id
	
LEFT JOIN fty.league_competitor as lc ON activity.season = lc.season
	AND activity.platform = lc.platform
	AND activity.league_id = lc.league_id
	AND activity.competitor_id = lc.competitor_id