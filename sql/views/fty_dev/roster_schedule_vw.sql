create or replace view fty_dev.roster_schedule_vw as

-- Player identity comes from fty_dev.player_vw, which resolves the fantasy id to the
-- canonical nba player_id and conformed name (replacing util.conformed_player_id_RETIRED).
-- player_vw emits lower case platform, hence lower(roster.platform).

select
    roster.season,
    roster.platform,
    roster.league_id,
    roster.assigned_date,
    roster.matchup_period,
    schedule_dates.matchup_start,
    schedule_dates.matchup_end,
    roster.competitor_id,
    competitor.competitor_name,
    roster.player_fantasy_id,
    plyr.player_id,
    plyr.player_name,
    roster.player_team,
    roster.player_injury_status,
    roster.player_acquisition_type,
    schedule.opponent_id::bigint as opponent_id,
    opponent.competitor_name     as opponent_name
from fty_dev.competitor_roster roster
    left join fty_dev.league_matchup schedule
        on roster.season = schedule.season
       and roster.platform = schedule.platform
       and roster.league_id = schedule.league_id
       and roster.competitor_id = schedule.competitor_id
       and roster.matchup_period = schedule.matchup_period
    left join fty_dev.league_matchup_dates schedule_dates
        on roster.season = schedule_dates.season
       and roster.platform = schedule_dates.platform
       and roster.league_id = schedule_dates.league_id
       and roster.matchup_period = schedule_dates.matchup_period
    left join fty_dev.league_competitor competitor
        on roster.season = competitor.season
       and roster.platform = competitor.platform
       and roster.league_id = competitor.league_id
       and roster.competitor_id = competitor.competitor_id
    left join fty_dev.league_competitor opponent
        on roster.season = opponent.season
       and roster.platform = opponent.platform
       and roster.league_id = opponent.league_id
       and schedule.opponent_id = opponent.competitor_id::double precision
    left join fty_dev.player_vw plyr
        on plyr.platform = lower(roster.platform)
       and plyr.fantasy_id = roster.player_fantasy_id
