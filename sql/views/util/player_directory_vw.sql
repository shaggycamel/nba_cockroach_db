create or replace view util.player_directory_vw as

-- Every (season, platform, source_id) a player is known by, across nba, statyx and the
-- fantasy platforms. Feeds util.active_player_vw and util.unmatched_player_source_vw.
--
-- The fantasy legs read fty (formerly fty_dev). ESPN coverage is identical between the two
-- schemas across 2023-24/2024-25/2025-26; the Yahoo league is retired, so the 2024-25
-- Yahoo league (121793) no longer appears here. Its id mappings remain in
-- util.player_source_id.

select
    s.season,
    'nba'::text as platform,
    b.player_id as source_id,
    b.player_name as source_name
from nba.player_box_score b
    join (
        select distinct game_id, season
        from nba.league_game_schedule
    ) s using (game_id)
where b.player_id is not null and b.player_id < 100000000

union

select
    r.season,
    'nba'::text as platform,
    r.player_id::bigint as source_id,
    r.player as source_name
from nba.team_roster r
where r.player_id is not null

union

select
    pi.season,
    'statyx'::text as platform,
    pi.player_id as source_id,
    pi.full_name as source_name
from statyx.player_info pi
where pi.player_id is not null

union

select
    fa.season,
    lower(fa.platform) as platform,
    fa.player_id as source_id,
    fa.player_name as source_name
from fty.free_agents fa
where fa.player_id is not null

union

select
    cr.season,
    lower(cr.platform) as platform,
    cr.player_fantasy_id as source_id,
    cr.player_name as source_name
from fty.competitor_roster cr
where cr.player_fantasy_id is not null
