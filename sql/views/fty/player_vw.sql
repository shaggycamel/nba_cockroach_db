create or replace view fty.player_vw as

-- Resolves a fantasy platform's player id to the canonical nba player id and name.
-- Replaces util.conformed_player_id_RETIRED.
--
-- platform is emitted lower case, as util.player_source_id stores it. Consumers in
-- fty join with lower(x.platform), matching util.player_directory_vw's convention.
--
-- 37 player_keys carry two nba source ids (name collisions and truncated/legacy ids),
-- which would otherwise fan a single roster row out into two. DISTINCT ON keeps the id
-- with the most box score rows, which is the established player in every observed case.

with nba_id as (
    select distinct on (psi.player_key)
        psi.player_key,
        psi.source_id as player_id
    from util.player_source_id psi
    left join (
        select player_id, count(*) as box_rows
        from nba.player_box_score
        group by player_id
    ) bx on bx.player_id = psi.source_id
    where psi.platform = 'nba'
    order by psi.player_key, coalesce(bx.box_rows, 0) desc, psi.source_id
)

select
    src.platform,
    src.source_id as fantasy_id,
    src.source_name as fantasy_name,
    src.player_key,
    nba_id.player_id,
    p.conformed_name as player_name
from util.player_source_id src
    left join nba_id on nba_id.player_key = src.player_key
    left join util.player p on p.player_key = src.player_key
where src.platform <> 'nba'
