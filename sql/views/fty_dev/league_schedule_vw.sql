create or replace view fty_dev.league_schedule_vw as

-- league_matchup.opponent_id is double precision in fty_dev; cast to bigint so consumers
-- join cleanly against competitor_id (fty's view cast the other direction instead).
--
-- A bye has two representations in the source data, and is_bye normalises both:
--   2024-25 - a league_matchup row exists with opponent_id null
--   2025-26 - no league_matchup row at all; the fact lives only in league_byes, so those
--             competitors have to be unioned back in or they vanish from the schedule

select
    mup_dates.season,
    mup_dates.platform,
    mup_dates.league_id,
    mup_dates.matchup_period,
    mup_dates.matchup_start,
    mup_dates.matchup_end,
    mup.competitor_id,
    mup.opponent_id::bigint as opponent_id,
    mup.competitor_id is not null and mup.opponent_id is null as is_bye
from fty_dev.league_matchup_dates mup_dates
    left join fty_dev.league_matchup mup
        on mup_dates.season = mup.season
       and mup_dates.platform = mup.platform
       and mup_dates.league_id = mup.league_id
       and mup_dates.matchup_period = mup.matchup_period

union all

select
    mup_dates.season,
    mup_dates.platform,
    mup_dates.league_id,
    mup_dates.matchup_period,
    mup_dates.matchup_start,
    mup_dates.matchup_end,
    bye.competitor_id,
    null::bigint as opponent_id,
    true as is_bye
from fty_dev.league_byes bye
    join fty_dev.league_matchup_dates mup_dates
        on mup_dates.season = bye.season::text
       and mup_dates.platform = bye.platform::text
       and mup_dates.league_id = bye.league_id
       and mup_dates.matchup_period = bye.matchup_period
