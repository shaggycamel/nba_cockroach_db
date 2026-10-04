create or replace view fty.base_vw as

select
    lc.season,
    lc.platform,
    lc.league_id,
    lc.competitor_id,
    lc.competitor_abbrev,
    lc.competitor_name,
    lg.league_name
from fty.league_competitor lc
    left join fty.league lg
        on lc.league_id = lg.league_id
       and lc.season = lg.season
       and lc.platform = lg.platform
order by lower(lc.competitor_name)
