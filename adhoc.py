from polars_conversion import dataHub
import polars as pl
import polars.selectors as cs
import janitor.polars
import dateutil
import datetime as dt
import zoneinfo
import time
import sqlalchemy
import nba_api.stats.endpoints as nba_ep



dh = dataHub('postgre')


col_order = (
    pl.read_database(
        "SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order", 
        dh.db_con
    )
    .get_column('column_name')
    .to_list()
)

season = dh.cur_season_year
# if season == 'current':
#     season = self.cur_season_year
# else:
#     season = self.prev_season_year

print('\n--------------------- nba.historical_league_game_schedule')
dfs = [] 
for type_season in ['Regular Season', 'Pre Season', 'Playoffs', 'All Star']:
    hist_game_schedule = nba_ep.leaguegamelog.LeagueGameLog(season_type_all_star=type_season, season=season)
    dfs.append((
        pl.from_pandas(hist_game_schedule.get_data_frames()[0])
        .with_columns(pl.lit(type_season).alias('season_type'))
    ))
    time.sleep(1)

df = (
    pl.concat(dfs)
    .clean_names()
    .with_columns([
        pl.col('game_id').cast(pl.Float64),
        pl.col('game_date').str.to_date(),
        pl.lit(f'{season}-{str(season+1)[-2:]}').alias('season'),
        pl.col('matchup').str.replace_all(r' @ | vs\.? ', '-').alias('opponent')
    ])
    .with_columns(pl.col('opponent').str.split('-'))
    .with_columns(
        pl.when(pl.col('team_abbreviation') == pl.col('opponent').list.get(0))
        .then(pl.col('opponent').list.get(1))
        .otherwise(pl.col('opponent').list.get(0))
        .alias('opponent')
    )
    .with_columns([
        pl.when(pl.col('wl') == 'W').then(pl.col('team_abbreviation')).otherwise(pl.col('opponent')).alias('team_winner'),
        pl.when(pl.col('wl') == 'L').then(pl.col('team_abbreviation')).otherwise(pl.col('opponent')).alias('team_loser')
    ])
    .select(col_order)
)


db_ex = self.db_con.connect()
db_ex.execute(sqlalchemy.sql.text(f"DELETE FROM nba.league_game_schedule WHERE season = '{season}-{str(season+1)[-2:]}'"))
db_ex.commit()

df.to_pandas().to_sql('league_game_schedule', self.db_con, schema='nba', index=False, if_exists='append')
print('nba.historical_game_schedule has been updated\n\n')