import configparser
import snakecase
import re
import espn_api.basketball as bb
from os import getcwd
from requests import get
from datetime import datetime, timedelta
from dateutil.parser import parse
from pytz import timezone
from time import sleep
from tabula import read_pdf
from bs4 import BeautifulSoup
from unicodedata import normalize
from pandas import DataFrame, concat, read_sql, to_datetime, date_range, merge
from numpy import where, nan
from sqlalchemy import create_engine
from sqlalchemy.sql import text
from pandasql import sqldf; pysqldf = lambda q: sqldf(q, locals())
from nba_api.stats.endpoints import playercareerstats, commonplayerinfo, playergamelog, leaguegamelog, commonteamroster, boxscoreadvancedv2, boxscoretraditionalv3 #, boxscoretraditionalv2
from nba_api.stats.static import players, teams
from nba_api.stats.library.parameters import Season
from yfpy.query import YahooFantasySportsQuery

# Constants
timeout = 3 * 60 # 5 minute timeout


class dataHub:
    
    def __init__(self, platform):

        # Scalars
        self.cur_season = Season.current_season
        self.cur_season_year = int(Season.current_season[0:4])
        # self.cur_season = '2024-25'
        # self.cur_season_year = 2024
        self.prev_season = Season.previous_season
        self.prev_season_year = int(Season.previous_season[0:4])
        self.cur_date_est = datetime.now(timezone('US/Eastern')).date()
        self.db_con = self._db_connect(platform)
        self.fty_con = self._fty_con()

        # Data objects
        self.nba_teams = DataFrame(teams.get_teams())
        self.active_players = DataFrame(players.get_active_players())

    
    def _db_connect(self, platform):
        """ Establish connection to desired platform """
        parser = configparser.ConfigParser()
        parser.read(getcwd() + '/database.ini')
        db_creds = dict(parser.items(platform))
        sql_url = 'dialect://user:password@host:port/database'
        for el in db_creds: 
            sql_url = sql_url.replace(el, db_creds[el])

        return create_engine(sql_url, connect_args={'connect_timeout': timeout})
        

    
    def get_player_season_stats(self):
        """ Season stats (totals) """

        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'player_season_stats' ORDER BY column_order", self.db_con)['column_name'].to_list()
        ls_pl = self.active_players['id'].to_list() #[480:571]

        print('\n--------------------- nba.player_season_stats')
        dfs = []
        for player in ls_pl:
            player_season = playercareerstats.PlayerCareerStats(player_id=str(player))
            player_season = player_season.data_sets[0].get_data_frame()
            dfs.append(player_season)
            ix = ls_pl.index(player)
            if ix % 50 == 0: 
                print('player:', ix, '/', len(ls_pl))
            sleep(1)
        print('player:', ix, '/', len(ls_pl))

        # Clean up for ingestion into database
        df = concat(dfs, ignore_index=True)
        df = df.rename(snakecase.convert, axis='columns')
        df = df.rename(columns = {'season_id': 'season'})
        df = df[df['season'] == self.cur_season]
        df = df[col_order]

        # Write to database
        df.to_sql('player_season_stats', self.db_con, schema='nba', index=False, if_exists='append')
        print('nba.player_season_stats has been updated\n\n')
        


    