create or replace view fty_dev.free_agents_vw as

-- free_agents.player_id holds the PLATFORM's player id (e.g. ESPN 3202 = Kevin Durant),
-- so it is exposed as fantasy_id and the real nba player_id is resolved via player_vw.

select
    fa.season,
    fa.platform,
    fa.league_id,
    plyr.player_id,
    fa.player_id as fantasy_id,
    plyr.player_name,
    fa.player_team,
    fa.player_injury_status,
    fa.player_position
from fty_dev.free_agents fa
    left join fty_dev.player_vw plyr
        on plyr.platform = lower(fa.platform)
       and plyr.fantasy_id = fa.player_id
