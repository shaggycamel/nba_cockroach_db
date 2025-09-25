import pandas as pd
from datetime import datetime, timedelta
from dataHub import dataHub

dh = dataHub('postgre')

league_cats = pd.read_sql(f"SELECT * FROM fty.league_categories WHERE platform = 'ESPN' AND season = '2024-25' AND league_id = 95537", dh.db_con)

cat_labels = (
    league_cats
    .merge(pd.read_sql("SELECT * FROM fty.category_label WHERE platform = 'ESPN'", dh.db_con), how='left', left_on=['platform', 'category'], right_on=['platform', 'fty_category'])
    .set_index('fty_category')['db_category']
    .to_dict()
)


# Matchup period and dates ----------------------------------------------------

nba_match_dates = []
p_sch = dh.fty_con['ESPN;95537'].pro_schedule
for team in p_sch:
    for match_day in p_sch[team]:
        nba_match_dates.append({
            'match_day': int(match_day), 
            'date': datetime.fromtimestamp(p_sch[team][match_day][0]['date'] / 1000).date() - timedelta(days=1)
            # minus one day to get the conversion right
        })

nba_match_dates = (
    pd.DataFrame(nba_match_dates)
    .drop_duplicates()
    .sort_values('match_day')
)


fty_matchup_dates = dh.fty_con['ESPN;95537'].matchup_ids
fty_matchup_dates = pd.DataFrame([(int(mp), int(md)) for mp, days in fty_matchup_dates.items() for md in days], columns=['matchup_period', 'match_day'])
fty_matchup_dates = fty_matchup_dates[fty_matchup_dates['match_day'].isin(fty_matchup_dates.groupby('matchup_period')['match_day'].agg(['min','max']).stack())]
fty_matchup_dates = fty_matchup_dates.sort_values(['matchup_period', 'match_day'])
fty_matchup_dates = fty_matchup_dates.merge(nba_match_dates, on = 'match_day', how = 'left')

grp_min = fty_matchup_dates.groupby('matchup_period')['match_day'].transform('min')
grp_max = fty_matchup_dates.groupby('matchup_period')['match_day'].transform('max')

fty_matchup_dates['from_to'] = None
fty_matchup_dates.loc[fty_matchup_dates['match_day'] == grp_min, 'from_to'] = 'matchup_start'
fty_matchup_dates.loc[fty_matchup_dates['match_day'] == grp_max, 'from_to'] = 'matchup_end'

fty_matchup_dates = (
    fty_matchup_dates
    .pivot(index='matchup_period', columns='from_to', values='date')
    .rename_axis(columns=None)
    .reset_index()
    .assign(season = '2024-25', platform = 'ESPN', league_id = 123)
)

# League Schedule ----------------------------------------------------

lgs_sch = []
for competitor in dh.fty_con['ESPN;95537'].teams:
    for ix, opponent in enumerate(competitor.schedule):
        lgs_sch.append({
            'matchup_period': ix + 1, 
            'competitor_id': competitor.team_id, 
            'opponent_id': opponent.home_team.team_id if competitor.team_id == opponent.away_team.team_id else opponent.away_team.team_id
        })

lgs_sch = (
    pd.DataFrame(lgs_sch)
    .sort_values(['matchup_period', 'competitor_id'])
)
