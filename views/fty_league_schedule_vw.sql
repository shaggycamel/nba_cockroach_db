create or replace view fty.fty_league_schedule_vw as

SELECT mup_dates.season,
    mup_dates.platform,
    mup_dates.league_id,
    mup_dates.matchup_period,
    mup_dates.matchup_start,
    mup_dates.matchup_end,
    mup.competitor_id,
    mup.opponent_id
   FROM fty.league_matchup_dates mup_dates
     LEFT JOIN fty.league_matchup mup ON mup_dates.season = mup.season AND mup_dates.platform = mup.platform AND mup_dates.league_id = mup.league_id AND mup_dates.matchup_period = mup.matchup_period;