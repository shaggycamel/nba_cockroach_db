create or replace view util.player_id_map_vw as

-- One row per player, with that player's id and name on each source platform.
-- Replaces util.conformed_player_id_RETIRED, built from util.player + util.player_source_id.
--
-- Some player_keys carry more than one id on a platform (37 on nba, 6 each on espn and
-- statyx) from name collisions, truncated ids and bad merges. One id is chosen per
-- player_key per platform, preferring in order:
--   1. an id that still appears in util.player_directory_vw (ie is live in source data)
--   2. an id whose source name matches the conformed name (catches merges such as the
--      statyx id named 'Armel Traore' sitting under conformed 'Nolan Traore')
--   3. for nba, the id with the most box score rows (the established player)
--   4. the highest id, as a deterministic tie break

with dir as (
    select distinct platform, source_id
    from util.player_directory_vw
),

box as (
    select player_id, count(*) as box_rows
    from nba.player_box_score
    group by player_id
),

ranked as (
    select
        psi.player_key,
        psi.platform,
        psi.source_id,
        psi.source_name,
        row_number() over (
            partition by psi.player_key, psi.platform
            order by
                (dir.source_id is not null) desc,
                (psi.source_name = p.conformed_name) desc,
                coalesce(box.box_rows, 0) desc,
                psi.source_id desc
        ) as rn
    from util.player_source_id psi
        join util.player p
            on p.player_key = psi.player_key
        left join dir
            on dir.platform = psi.platform
           and dir.source_id = psi.source_id
        left join box
            on psi.platform = 'nba'
           and box.player_id = psi.source_id
)

select
    p.player_key,
    p.conformed_name,
    max(r.source_id)   filter (where r.platform = 'nba')    as nba_id,
    max(r.source_name) filter (where r.platform = 'nba')    as nba_name,
    max(r.source_id)   filter (where r.platform = 'espn')   as espn_id,
    max(r.source_name) filter (where r.platform = 'espn')   as espn_name,
    max(r.source_id)   filter (where r.platform = 'yahoo')  as yahoo_id,
    max(r.source_name) filter (where r.platform = 'yahoo')  as yahoo_name,
    max(r.source_id)   filter (where r.platform = 'statyx') as statyx_id,
    max(r.source_name) filter (where r.platform = 'statyx') as statyx_name
from util.player p
    left join ranked r
        on r.player_key = p.player_key
       and r.rn = 1
group by p.player_key, p.conformed_name
