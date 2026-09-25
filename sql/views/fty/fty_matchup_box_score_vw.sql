CREATE OR REPLACE view fty.fty_matchup_box_score_vw AS

SELECT bs.season,
    bs.platform,
    bs.league_id,
    bs.competitor_id,
    bs.matchup,
    bs.pts,
    bs.blk,
    bs.stl,
    bs.ast,
    bs.reb,
    bs.tov,
    bs.fgm,
    bs.fga,
    bs.ftm,
    bs.fta,
    bs.fg3_m,
    bs.fg_pct,
    bs.ft_pct,
    bs.dd2,
    bs.td3,
    competitor.competitor_abbrev,
    competitor.competitor_name
   FROM fty.matchup_box_score bs
     LEFT JOIN fty.league_competitor competitor ON bs.competitor_id = competitor.competitor_id AND bs.league_id = competitor.league_id AND bs.platform = competitor.platform AND bs.season = competitor.season;

