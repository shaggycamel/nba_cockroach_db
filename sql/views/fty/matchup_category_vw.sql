create or replace view fty.matchup_category_vw as

-- Long form matchup results, one row per competitor per category.
-- Reads the scored categories from categories_vw. A ratio category (fg_pct) is built
-- from its numerator/denominator, which live in matchup_box_score even when the league
-- does not score them; a points league gets fantasy_points instead.

select
    c.season,
    c.platform,
    c.league_id,
    bs.matchup,
    bs.competitor_id,
    c.nba_category as category,
    c.fmt_category,
    c.display_order,
    c.scoring_type,
    c.scoring_format,
    c.higher_is_better,
    case
        when c.is_ratio then coalesce(num.value / nullif(den.value, 0), 0)
        else bs.value
    end as value,
    case
        when c.points is not null then bs.value * c.points
        else null::double precision
    end as fantasy_points
from fty.categories_vw c
    join fty.matchup_box_score bs
        on bs.season = c.season
       and bs.platform = c.platform
       and bs.league_id = c.league_id
       and bs.category = coalesce(c.numerator, c.nba_category)
    left join fty.matchup_box_score num
        on num.season = c.season
       and num.platform = c.platform
       and num.league_id = c.league_id
       and num.matchup = bs.matchup
       and num.competitor_id = bs.competitor_id
       and num.category = c.numerator
    left join fty.matchup_box_score den
        on den.season = c.season
       and den.platform = c.platform
       and den.league_id = c.league_id
       and den.matchup = bs.matchup
       and den.competitor_id = bs.competitor_id
       and den.category = c.denominator
where c.category_role = 'scored'
