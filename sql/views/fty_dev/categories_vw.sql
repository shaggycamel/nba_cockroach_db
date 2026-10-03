create or replace view fty_dev.categories_vw as

-- One row per league per category, tagged with the role that category plays.
--
--   scored    - what the league actually plays, from league_categories
--   component - fgm/fga/ftm/fta. A league that scores FG% usually does not score its
--               components, but matchup_box_score always stores them and never stores
--               the ratio, so they must stay fetchable. calc_z_pcts() needs them for
--               every league regardless of scoring. Suppressed where already scored.
--   derived   - all_cat / fg_z / ft_z. Computed in R, never in league_categories.

-- scored -----------------------------------------------------------------
select
    lc.season,
    lc.platform,
    lc.league_id,
    lc.category                     as platform_category,
    cl.nba_category,
    cl.fmt_category,
    cl.display_order,
    lc.points,
    cl.higher_is_better,
    cl.numerator,
    cl.denominator,
    cl.numerator is not null        as is_ratio,
    'scored'                        as category_role,
    lg.scoring_type,
    sf.scoring_format
from fty_dev.league_categories lc
    join fty_dev.platform_category pc
        on pc.platform = lc.platform
       and pc.platform_category = lc.category
    join fty_dev.category_label cl
        on cl.nba_category = pc.nba_category
    left join fty_dev.league lg
        on lg.season = lc.season
       and lg.platform = lc.platform
       and lg.league_id = lc.league_id
    left join fty_dev.scoring_format sf
        on sf.platform = lg.platform
       and sf.scoring_type = lg.scoring_type::text

union all

-- component --------------------------------------------------------------
select
    lg.season,
    lg.platform,
    lg.league_id,
    null::text                      as platform_category,
    cl.nba_category,
    cl.fmt_category,
    cl.display_order,
    null::double precision          as points,
    cl.higher_is_better,
    cl.numerator,
    cl.denominator,
    false                           as is_ratio,
    'component'                     as category_role,
    lg.scoring_type,
    sf.scoring_format
from fty_dev.league lg
    cross join fty_dev.category_label cl
    left join fty_dev.scoring_format sf
        on sf.platform = lg.platform
       and sf.scoring_type = lg.scoring_type::text
where cl.nba_category in ('fgm', 'fga', 'ftm', 'fta')
  and not exists (
        select 1
        from fty_dev.league_categories lc
            join fty_dev.platform_category pc
                on pc.platform = lc.platform
               and pc.platform_category = lc.category
        where lc.season = lg.season
          and lc.platform = lg.platform
          and lc.league_id = lg.league_id
          and pc.nba_category = cl.nba_category
  )

union all

-- derived ----------------------------------------------------------------
select
    lg.season,
    lg.platform,
    lg.league_id,
    null::text                      as platform_category,
    cl.nba_category,
    cl.fmt_category,
    cl.display_order,
    null::double precision          as points,
    cl.higher_is_better,
    cl.numerator,
    cl.denominator,
    cl.numerator is not null        as is_ratio,
    'derived'                       as category_role,
    lg.scoring_type,
    sf.scoring_format
from fty_dev.league lg
    cross join fty_dev.category_label cl
    left join fty_dev.scoring_format sf
        on sf.platform = lg.platform
       and sf.scoring_type = lg.scoring_type::text
where cl.nba_category in ('all_cat', 'fg_z', 'ft_z')
