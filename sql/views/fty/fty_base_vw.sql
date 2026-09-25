create or replace view fty.fty_base_vw as

SELECT lc.season,
    lc.platform,
    lc.league_id,
    lc.competitor_id,
    lc.competitor_abbrev,
    lc.competitor_name,
    lg.league_name
   FROM fty.league_competitor lc
     LEFT JOIN fty.league lg ON lc.league_id = lg.league_id AND lc.season = lg.season
  ORDER BY (lower(lc.competitor_name))