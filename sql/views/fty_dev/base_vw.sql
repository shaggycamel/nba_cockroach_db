create or replace view fty_dev.base_vw as

select
    lc.season,
    lc.platform,
    lc.league_id,
    lc.competitor_id,
    lc.competitor_abbrev,
    lc.competitor_name,
    lg.league_name
from fty_dev.league_competitor lc
    left join fty_dev.league lg
        on lc.league_id = lg.league_id
       and lc.season = lg.season
       and lc.platform = lg.platform
order by lower(lc.competitor_name)
