from dataHub import dataHub

dh = dataHub('postgre')
# dh = dataHub('cockroach')

# ---------------------------------- NBA Data

# ---- Player Season Stats - DONE 2025-26
# dh.get_player_season_stats()


# ----- Player info - DONE 2025-26
# dh.get_player_info()


# ----- Injuries - DAILY
# dh.get_team_injuries()


# ----- Game Schedule - DAILY - DONE 2025-26
# dh.update_past_game_schedule()
# dh.get_next_game_schedule()


# ----- Box Scores - DAILY
# dh.get_box_score()


# ----- Team Roster - REGULARLY - DONE 2025-26
# Also comprises of updating salaries. Look at player_salaries.py
# Eventually coportate this file into dataHub
# dh.get_team_roster()


# ---------------------------------- Fantasy Data

# ----- League Competitors - DONE 2025-26
# dh.fty_get_league_competitor()


# ----- Free Agents - DAILY
# dh.fty_get_free_agents()


# ----- Competitor Roster - DAILY
# dh.fty_get_competitor_roster()


# ----- Fantasy Matchup - DONE 2025-26
# dh.fty_get_league_matchup()


# ----- Fantasy Matchup dates
# dh.fty_get_league_matchup_dates()


# Matchup box scores - DAILY
# dh.fty_get_matchup_box_score()


# ----- Fantasy Transactions - DAILY
# dh.fty_get_recent_activity()

import configparser
import os
import requests
import tabula
import bs4
import sqlalchemy
import time
import zoneinfo
import dateutil
import datetime as dt
import polars as pl
import janitor.polars
import polars.selectors as cs
import nba_api.stats.endpoints as nba_ep
from nba_api.stats.static import teams, players
import nba_api.stats.library.parameters as nba_parameters
import espn_api.basketball as bb
from yfpy.query import YahooFantasySportsQuery as yfpy


col_order = pl.read_database(
    "SELECT column_name FROM util.table_column_order WHERE table_name = 'team_roster' ORDER BY column_order",
    dh.db_con,
)['column_name'].to_list()
teams = dh.nba_teams['id'].to_list()

print('\n--------------------- nba.team_roster')
dfs = []
for team in teams:
    common_teamroster = nba_ep.commonteamroster.CommonTeamRoster(
        season=dh.cur_season_year, team_id=team
    )
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
            pl.col('num').str.replace('', None),
            pl.lit(dh.cur_season).alias('season'),
            pl.lit(None).cast(pl.Float64).alias('salary'),
            pl.lit(None).cast(pl.Date).alias('movement_date'),
        ]
    )
    .join(dh.nba_teams, left_on='teamid', right_on='id', how='left')
    .rename({'teamid': 'team_id', 'abbreviation': 'team_slug'})
    .select(col_order)
)


df_existing = (
    pl.read_database(f"SELECT * FROM nba.team_roster WHERE season = '{dh.cur_season}'", dh.db_con)
    .with_columns(pl.col(col).cast(pl.Int64) for col in ['team_id', 'player_id'])
    .with_columns(
        pl.when(pl.col('movement_date').is_null())
        .then(pl.lit('2026-01-01').cast(pl.Date))  # change to self.date_est
        .otherwise(pl.col('movement_date'))  # check if this is needed
        .alias('movement_date')
    )
)


(
    pl.union([df, df_existing]).join(
        (
            df.join(df_existing, on=['season', 'team_id', 'player_id'], how='anti').select(
                'player_id'
            )
        ),
        on='player_id',
        how='inner',
    )
)

# fill in salary after join

# DOUBLE CHECK EVERYTHING....DOESN'T LOOK RIGHT
