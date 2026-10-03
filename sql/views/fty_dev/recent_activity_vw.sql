create or replace view fty_dev.recent_activity_vw as

select
    activity.season,
    activity.platform,
    activity.league_id,
    lgl.league_name,
    activity.competitor_id,
    lc.competitor_name,
    activity.player,
    activity.action,
    activity."timestamp"
from fty_dev.recent_activity activity
    left join fty_dev.league lgl
        on activity.season = lgl.season
       and activity.platform = lgl.platform
       and activity.league_id = lgl.league_id
    left join fty_dev.league_competitor lc
        on activity.season = lc.season
       and activity.platform = lc.platform
       and activity.league_id = lc.league_id
       and activity.competitor_id = lc.competitor_id
