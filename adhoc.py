from polars_conversion import dataHub
import polars as pl
import polars.selectors as cs
import janitor.polars
import datetime as dt
import zoneinfo
import time
import sqlalchemy
import requests
import dateutil
import nba_api.stats.endpoints as nba_ep

dh = dataHub('postgre')


# get_team_roster(self):

col_order = pl.read_database(
    "SELECT column_name FROM util.table_column_order WHERE table_name = 'team_roster' ORDER BY column_order",
    dh.db_con,
)['column_name'].to_list()
teams = dh.nba_teams['id'].to_list()

print('\n--------------------- nba.team_roster')
dfs = []

for team in teams[0:3]:
    common_teamroster = nba_ep.commonteamroster.CommonTeamRoster(season=dh.cur_season_year, team_id=team)
    dfs.append(pl.from_pandas(common_teamroster.get_data_frames()[0]))
    ix = teams.index(team)
    if ix % 5 == 0:
        print('team:', ix, '/', len(teams))
    time.sleep(1)
print('team:', ix, '/', len(teams))

df = (
    pl.concat(dfs)
    .clean_names()
    .with_columns(
        [
            pl.col('num').replace('', None),
            pl.lit(dh.cur_season).alias('season'),
            pl.lit(None).cast(pl.Float64).alias('salary'),
            pl.lit(None).cast(pl.Date).alias('movement_date'),
        ]
    )
    .join(dh.nba_teams, left_on='teamid', right_on='id', how='left')
    .rename({'teamid': 'team_id', 'abbreviation': 'team_slug'})
    .select(col_order)
)

# CONTROL FOR PLAYERS BEING TRADED
# df_t = read_sql(f"SELECT * FROM nba.team_roster WHERE season = '{self.cur_season}'", db_con)
# df_t = df_t.drop('salary', axis='columns')
# df = concat([df, df_t])
# df = df[~df.duplicated(keep = False)].reset_index(drop=True)

# Write to database
df.to_pandas().to_sql('team_roster', dh.db_con, schema='nba', index=False, if_exists='append')
print('nba.team_roster has been updated\n\n')
