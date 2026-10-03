create or replace view fty_dev.matchup_box_score_vw as

-- Pivots the long matchup_box_score back to one column per stat.
-- fgm/fga/ftm/fta are emitted whether or not the league scores them: calc_z_pcts() in
-- the R package needs them for every league, and the fg_pct/ft_pct ratios are derived
-- here rather than stored.

select
    bs.season,
    bs.platform,
    bs.league_id,
    bs.competitor_id,
    bs.matchup,
    max(bs.value) filter (where bs.category = 'pts')   as pts,
    max(bs.value) filter (where bs.category = 'blk')   as blk,
    max(bs.value) filter (where bs.category = 'stl')   as stl,
    max(bs.value) filter (where bs.category = 'ast')   as ast,
    max(bs.value) filter (where bs.category = 'reb')   as reb,
    max(bs.value) filter (where bs.category = 'tov')   as tov,
    max(bs.value) filter (where bs.category = 'fgm')   as fgm,
    max(bs.value) filter (where bs.category = 'fga')   as fga,
    max(bs.value) filter (where bs.category = 'ftm')   as ftm,
    max(bs.value) filter (where bs.category = 'fta')   as fta,
    max(bs.value) filter (where bs.category = 'fg3_m') as fg3_m,
    coalesce(
        max(bs.value) filter (where bs.category = 'fgm')
        / nullif(max(bs.value) filter (where bs.category = 'fga'), 0),
        0
    ) as fg_pct,
    coalesce(
        max(bs.value) filter (where bs.category = 'ftm')
        / nullif(max(bs.value) filter (where bs.category = 'fta'), 0),
        0
    ) as ft_pct,
    max(bs.value) filter (where bs.category = 'dd2')   as dd2,
    max(bs.value) filter (where bs.category = 'td3')   as td3,
    lc.competitor_abbrev,
    lc.competitor_name
from fty_dev.matchup_box_score bs
    left join fty_dev.league_competitor lc
        on bs.season = lc.season
       and bs.platform = lc.platform
       and bs.league_id = lc.league_id
       and bs.competitor_id = lc.competitor_id
group by bs.season, bs.platform, bs.league_id, bs.competitor_id, bs.matchup,
         lc.competitor_abbrev, lc.competitor_name
