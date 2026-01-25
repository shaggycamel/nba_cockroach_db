import configparser
import snakecase
import re
import os
import requests
import tabula
import bs4
import unicodedata
import sqlalchemy
import time
import zoneinfo
import dateutil
import janitor
import datetime as dt
import numpy as np
import polars as pl
import polars.selectors as cs
import nba_api.stats.endpoints as nba_ep
from nba_api.stats.static import teams, players
import nba_api.stats.library.parameters as nba_parameters
import espn_api.basketball as bb
from yfpy.query import YahooFantasySportsQuery as yfpy

from pandasql import sqldf

pysqldf = lambda q: sqldf(q, locals())


# Constants
timeout = 3 * 60  # 5 minute timeout


class dataHub:
    def __init__(self, platform):
        # Scalars
        self.cur_season = nba_parameters.Season.current_season
        self.cur_season_year = int(nba_parameters.Season.current_season[0:4])
        # self.cur_season = '2024-25'
        # self.cur_season_year = 2024
        self.prev_season = nba_parameters.Season.previous_season
        self.prev_season_year = int(nba_parameters.Season.previous_season[0:4])
        self.db_con = self._db_connect(platform)
        self.fty_con = self._fty_con()

        # Data objects
        self.nba_teams = pl.DataFrame(teams.get_teams())
        self.active_players = pl.DataFrame(players.get_active_players())

    def _db_connect(self, platform):
        """Establish connection to desired platform"""
        parser = configparser.ConfigParser()
        parser.read(os.getcwd() + '/database.ini')
        db_creds = dict(parser.items(platform))
        sql_url = 'dialect://user:password@host:port/database'
        for el in db_creds:
            sql_url = sql_url.replace(el, db_creds[el])

        return sqlalchemy.create_engine(sql_url, connect_args={'connect_timeout': timeout})

    def get_player_season_stats(self):
        """Season stats (totals)"""

        col_order = pl.read_database(
            "SELECT column_name FROM util.table_column_order WHERE table_name = 'player_season_stats' ORDER BY column_order",
            self.db_con,
        )['column_name'].to_list()
        ls_pl = self.active_players['id'].to_list()  # [480:571]

        print('\n--------------------- nba.player_season_stats')
        dfs = []
        for player in ls_pl:
            player_season = nba_ep.playercareerstats.PlayerCareerStats(player_id=str(player))
            player_season = pl.from_pandas(player_season.data_sets[0].get_data_frame())
            dfs.append(player_season)
            ix = ls_pl.index(player)
            if ix % 50 == 0:
                print('player:', ix, '/', len(ls_pl))
            time.sleep(1)
        print('player:', ix, '/', len(ls_pl))

        # Clean up for ingestion into database
        df = (
            pl.concat(dfs)
            .clean_names()
            .rename({'season_id': 'season', 'fg3m': 'fg3_m', 'fg3a': 'fg3_a'})
            .with_columns(pl.lit(self.cur_season).alias('season'))
            .select(col_order)
        )

        # Write to database
        df.to_pandas().to_sql(
            'player_season_stats', self.db_con, schema='nba', index=False, if_exists='append'
        )
        print('nba.player_season_stats has been updated\n\n')

    def get_player_info(self):
        col_order = pl.read_database(
            "SELECT column_name FROM util.table_column_order WHERE table_name = 'player_info' ORDER BY column_order",
            self.db_con,
        )['column_name'].to_list()
        ls_pl = self.active_players['id'].to_list()  # [550:615]

        print('\n--------------------- nba.player_info')
        dfs = []
        for player in ls_pl:
            player_info = nba_ep.commonplayerinfo.CommonPlayerInfo(player_id=str(player))
            player_info = pl.from_pandas(player_info.data_sets[0].get_data_frame())
            dfs.append(player_info)
            ix = ls_pl.index(player)
            if ix % 50 == 0:
                print('player:', ix, '/', len(ls_pl))
            time.sleep(1)
        print('player:', ix, '/', len(ls_pl))

        # # Clean up for ingestion into database
        df = (
            pl.concat(dfs)
            .clean_names()
            .with_columns(pl.col('height').str.split_exact('-', n=1).cast(pl.Float64))
            .with_columns(
                [
                    pl.lit(self.cur_season).alias('season'),
                    (pl.col('weight').cast(pl.Float64, strict=False) / 2.2046)
                    .round(3)
                    .alias('weight_kg'),
                    ((pl.col('height').list.get(0) * 12 + pl.col('height').list.get(1)) * 2.54)
                    .round(2)
                    .alias('height_cm'),
                ]
            )
            .rename({'person_id': 'player_id'})
            .select(col_order)
        )

        # Write to database
        df.to_pandas().to_sql(
            'player_info', self.db_con, schema='nba', index=False, if_exists='append'
        )
        print('nba.player_info has been updated\n\n')

    def get_team_injuries(self):
        col_order = pl.read_database(
            "SELECT column_name FROM util.table_column_order WHERE table_name = 'injuries' ORDER BY column_order",
            self.db_con,
        )['column_name'].to_list()
        url = f'https://official.nba.com/nba-injury-report-{self.cur_season}-season/'  # URL from which pdfs to be downloaded
        response = requests.get(
            url, headers={'User-Agent': 'Mozilla/5.0'}
        )  # Requests URL and get response object
        soup = bs4.BeautifulSoup(response.text, 'html.parser')  # Parse text obtained
        links = soup.find_all('a')  # Find all hyperlinks present on webpage

        # Get times of readings and select the latest
        readings_time = {}
        readings_pdf = {}
        for link in links:
            if link.decode_contents().endswith('ET report'):
                readings_time[link.contents[0]] = dateutil.parser.parse(
                    link.contents[0], fuzzy=True, ignoretz=True
                )
                readings_pdf[link.contents[0]] = requests.get(
                    link.get('href'), headers={'User-Agent': 'Mozilla/5.0'}
                )

        # Write pdf file
        pdf = open('injury.pdf', 'wb')
        pdf.write(readings_pdf[max(readings_time, key=readings_time.get)].content)
        pdf.close()

        # Where to search on pdf file
        top = 75
        left = 19
        width = 804
        height = 438
        dfs = tabula.read_pdf(
            'injury.pdf', area=[top, left, top + height, left + width], pages='all'
        )  # pdf pages
        dfs = [pl.from_pandas(el) for el in dfs]

        # Data objects used to reconcile and complimet injury date
        status_true = pl.DataFrame(
            {'Current Status': ['Available', 'Probable', 'Questionable', 'Out']}
        )
        teams_true = pl.read_database(
            "SELECT CONCAT(team_long, ' ', team_name) AS team, team_slug FROM nba.teams",
            self.db_con,
        ).rename({'team': 'Team'})

        cur_date = dt.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()
        game_ids = pl.read_database(
            f"SELECT game_date, game_id, matchup FROM nba.league_game_schedule WHERE game_date BETWEEN '{cur_date}' AND '{cur_date + dt.timedelta(days=2)}'",
            self.db_con,
        )
        game_ids = pl.concat(
            [
                game_ids.with_columns(pl.col('matchup').str.replace(' vs. ', '@')),
                (
                    game_ids.with_columns(
                        pl.col('matchup').str.split_exact(' vs. ', n=1)
                    ).with_columns(
                        (pl.col('matchup').list.get(1) + '@' + pl.col('matchup').list.get(0)).alias(
                            'matchup'
                        )
                    )
                ),
            ],
            how='diagonal',
        )

        player_ids = pl.read_database(
            'SELECT nba_name, nba_id FROM util.nba_fty_name_match', self.db_con
        ).with_columns(
            pl.col('nba_name').str.normalize('NFKD').str.replace_all('[^\\x00-\\x7F]', '')
        )

        # INNER FUNCTION
        def str_search(df, str_pat, col_ix, col_name):
            if df.filter(df[:, col_ix].str.contains(str_pat)).height == 0:
                df = df.insert_column(index=col_ix, column=pl.Series(col_name, [None] * df.height))
            else:
                df = df.rename({df.columns[col_ix]: col_name})
            return df

        # INNER FUNCTION
        def occ_count_search(df, df_true, col_ix, col_name):
            df_search = (
                pl.DataFrame({col_name: [el for el in df[:, col_ix]]}).group_by(col_name).len()
            )
            if (
                df_true.join(df_search, on=col_name, how='left').select(pl.col('len').sum()).item()
                == 0
            ):
                df = df.insert_column(index=col_ix, column=pl.Series(col_name, [None] * df.height))
            else:
                df = df.rename({df.columns[col_ix]: col_name})
            return df

        # Loop over pdf files, where the magic happens
        for ix, df in enumerate(dfs):
            if ix > 0:
                # Move column names to row, excluding first df
                colnames_temp = ['Unnamed: ' + str(el) for el in list(range(0, len(df.columns)))]
                df = pl.concat(
                    [
                        pl.DataFrame(
                            {
                                key: None if 'Unnamed' in val else val
                                for key, val in dict(zip(colnames_temp, df.columns)).items()
                            }
                        ),
                        df.rename(lambda c: colnames_temp[df.columns.index(c)]),
                    ],
                    how='vertical_relaxed',
                )

                # Column checks
                df = str_search(df, '/', 0, 'Game Date')  # first col date search
                df = str_search(df, ':', 1, 'Game Time')  # second col time search
                df = str_search(df, '@', 2, 'Matchup')  # third col matchup search
                df = occ_count_search(df, teams_true, 3, 'Team')  # fourth col test for team
                df = str_search(df, ',', 4, 'Player Name')  # fifth col test for player name
                df = occ_count_search(
                    df, status_true, 5, 'Current Status'
                )  # sixth col test for status
                df = df.rename({df.columns[6]: 'Reason'})  # straight rename of seventh column

            # assign back to index in list
            dfs[ix] = df

        # INNER FUNCTION: Define the combined expression logic
        def get_combined_expr(col):
            return pl.concat_str(
                [
                    pl.col(col).fill_null(''),
                    pl.col(col).shift(-1).fill_null(''),
                    pl.col(col).shift(-2).fill_null(''),
                ],
                separator=' ',
            ).str.strip_chars()

        # Fix poorly formatted injury rows AND clean up for ingestion
        df = (
            pl.concat(dfs)
            .with_columns(
                [
                    pl.col(['Game Date', 'Game Time', 'Matchup', 'Team'])
                    .fill_null(strategy='forward')
                    .fill_null(strategy='backward'),
                    pl.col('Reason').shift(-1).over('Team').alias('Reason_lead'),
                ]
            )
            # 1. Identify start of block to fix
            .with_columns(
                (
                    pl.col('Reason_lead').is_null()
                    & pl.col('Reason').str.starts_with('Injury/Illness')
                    & (pl.col('Team') == pl.col('Team').shift(-1))
                ).alias('is_start')
            )
            # 2. Add helper columns for Boolean mask and Group IDs
            .with_columns((pl.col('is_start').cast(pl.Int64).cum_sum()).alias('group_id'))
            # Fix poor formatting
            .with_columns(
                [
                    pl.when(
                        pl.col('is_start')
                        | pl.col('is_start').shift(1)
                        | pl.col('is_start').shift(2)
                    )
                    .then(get_combined_expr(col).first().over('group_id'))
                    .otherwise(pl.col(col))
                    .alias(col)
                    for col in ['Player Name', 'Current Status', 'Reason']
                ]
            )
            # Clean up
            .with_columns(pl.col('Player Name').str.split_exact(', ', n=1))
            .with_columns(
                [
                    pl.col('Game Date').str.to_date(format='%m/%d/%Y'),
                    (
                        pl.col('Player Name').list.get(1) + ' ' + pl.col('Player Name').list.get(0)
                    ).alias('Player Name'),
                ]
            )
            .drop(['is_start', 'group_id', 'Reason_lead'])
            .unique()
            .filter(
                (pl.col('Reason') != 'NOT YET SUBMITTED')
                & (pl.col('Player Name').is_not_null())
                & (pl.col('Game Date').is_not_null())
            )
            .join(teams_true, how='left', on='Team')
            .join(player_ids, how='left', left_on='Player Name', right_on='nba_name')
            .join(
                game_ids,
                how='left',
                left_on=['Game Date', 'Matchup'],
                right_on=['game_date', 'matchup'],
            )
            .clean_names()
            .rename({'current_status': 'status'})
            .select(col_order)
        )

        # Delete old records from database
        db_ex = self.db_con.connect()
        for row in df.iter_rows(named=True):
            game_date = row['game_date']
            game_id = row['game_id']
            player_name = row['player_name'].replace(
                "'", "''"
            )  # replace to handle single quotes if they exist
            db_ex.execute(
                sqlalchemy.sql.text(
                    f"DELETE FROM nba.injuries WHERE game_date = '{game_date}' AND game_id = {game_id} AND player_name = '{player_name}'"
                )
            )
        db_ex.commit()

        # Write to database
        df.to_pandas().to_sql(
            'injuries', self.db_con, schema='nba', index=False, if_exists='append'
        )
        print('nba.injuries has been updated\n\n')

    def get_box_score(self):
        bs_max_dt = (
            pl.read_database('SELECT MAX(game_date) FROM nba.nba_team_box_score_vw', self.db_con)
            .item()
            .strftime('%Y-%m-%d')
        )
        game_ids = pl.read_database(
            f"SELECT game_id, game_date FROM nba.league_game_schedule WHERE game_date > '{bs_max_dt}' AND game_date <= current_date",
            self.db_con,
        )
        trad_adv_lst = ['player', 'team']

        print('\n--------------------- nba.player/team_box_score')
        g_ids = game_ids.get_column('game_id').to_list()[0:3]
        for game_id in g_ids:
            game_id = '00' + str(int(game_id))
            print(game_id)

            dfs = []
            try:
                bst = nba_ep.boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
            except Exception as e:
                print(game_id + ': ' + str(e))
                continue

            for el in [0, 1]:
                bst_col_order = pl.read_database(
                    f"SELECT column_name FROM util.table_column_order WHERE table_name = '{trad_adv_lst[el]}_box_score_traditional' ORDER BY column_order",
                    self.db_con,
                )['column_name'].to_list()

                if el == 0:
                    bst_rename_dict = dict(
                        zip(
                            [
                                'gameId',
                                'teamId',
                                'teamTricode',
                                'personId',
                                'playerName',
                                'position',
                                'comment',
                                'minutes',
                                'fieldGoalsMade',
                                'fieldGoalsAttempted',
                                'fieldGoalsPercentage',
                                'threePointersMade',
                                'threePointersAttempted',
                                'threePointersPercentage',
                                'freeThrowsMade',
                                'freeThrowsAttempted',
                                'freeThrowsPercentage',
                                'points',
                                'reboundsOffensive',
                                'reboundsDefensive',
                                'reboundsTotal',
                                'assists',
                                'steals',
                                'blocks',
                                'turnovers',
                                'foulsPersonal',
                                'plusMinusPoints',
                            ],
                            bst_col_order,
                        )
                    )
                else:
                    bst_rename_dict = dict(
                        zip(
                            [
                                'gameId',
                                'teamId',
                                'teamTricode',
                                'minutes',
                                'fieldGoalsMade',
                                'fieldGoalsAttempted',
                                'fieldGoalsPercentage',
                                'threePointersMade',
                                'threePointersAttempted',
                                'threePointersPercentage',
                                'freeThrowsMade',
                                'freeThrowsAttempted',
                                'freeThrowsPercentage',
                                'points',
                                'reboundsOffensive',
                                'reboundsDefensive',
                                'reboundsTotal',
                                'assists',
                                'steals',
                                'blocks',
                                'turnovers',
                                'foulsPersonal',
                            ],
                            bst_col_order,
                        )
                    )

                df = (
                    pl.from_pandas(bst.get_data_frames()[el])
                    .rename({k: v for k, v in bst_rename_dict.items() if k != 'playerName'})
                    .with_columns(
                        [pl.col('min').str.replace('', None), pl.col('game_id').cast(pl.Int64)]
                    )
                    .with_columns(pl.col('min').str.replace(r':.*', '').cast(pl.Int64))
                )

                if el == 0:
                    df = df.with_columns(
                        (pl.col('firstName') + ' ' + pl.col('familyName')).alias('player_name')
                    )
                else:
                    df = (
                        df.group_by(['game_id', 'team_id', 'team_abbreviation'])
                        .agg(cs.numeric().sum())
                        .with_columns(
                            [
                                (pl.col('fgm') / pl.col('fga')).alias('fg_pct'),
                                (pl.col('fg3_m') / pl.col('fg3_a')).alias('fg3_pct'),
                                (pl.col('ftm') / pl.col('fta')).alias('ft_pct'),
                                pl.lit(None).alias('plus_minus'),  # just make none for place holder
                            ]
                        )
                    )

                df = df.unique().select(bst_col_order)
                dfs.append(df)

            dfs[0].to_pandas().to_sql(
                'player_box_score', self.db_con, schema='nba', index=False, if_exists='append'
            )
            dfs[1].to_pandas().to_sql(
                'team_box_score', self.db_con, schema='nba', index=False, if_exists='append'
            )

        print('nba.player/team_box_score have been updated\n\n')

    def update_past_game_schedule(self, season='current'):
        col_order = pl.read_database(
            "SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order",
            self.db_con,
        )['column_name'].to_list()

        if season == 'current':
            season = self.cur_season_year
        else:
            season = self.prev_season_year

        print('\n--------------------- nba.historical_league_game_schedule')
        dfs = []
        for type_season in ['Regular Season', 'Pre Season', 'Playoffs', 'All Star']:
            hist_game_schedule = nba_ep.leaguegamelog.LeagueGameLog(
                season_type_all_star=type_season, season=season
            )
            dfs.append(
                (
                    pl.from_pandas(hist_game_schedule.get_data_frames()[0]).with_columns(
                        pl.lit(type_season).alias('season_type')
                    )
                )
            )
            time.sleep(1)

        df = (
            pl.concat(dfs)
            .clean_names()
            .with_columns(
                [
                    pl.col('game_id').cast(pl.Float64),
                    pl.col('game_date').str.to_date(),
                    pl.lit(f'{season}-{str(season + 1)[-2:]}').alias('season'),
                    pl.col('matchup').str.replace_all(r' @ | vs\.? ', '-').alias('opponent'),
                ]
            )
            .with_columns(pl.col('opponent').str.split('-'))
            .with_columns(
                pl.when(pl.col('team_abbreviation') == pl.col('opponent').list.get(0))
                .then(pl.col('opponent').list.get(1))
                .otherwise(pl.col('opponent').list.get(0))
                .alias('opponent')
            )
            .with_columns(
                [
                    pl.when(pl.col('wl') == 'W')
                    .then(pl.col('team_abbreviation'))
                    .otherwise(pl.col('opponent'))
                    .alias('team_winner'),
                    pl.when(pl.col('wl') == 'L')
                    .then(pl.col('team_abbreviation'))
                    .otherwise(pl.col('opponent'))
                    .alias('team_loser'),
                ]
            )
            .select(col_order)
        )

        db_ex = self.db_con.connect()
        db_ex.execute(
            sqlalchemy.sql.text(
                f"DELETE FROM nba.league_game_schedule WHERE season = '{season}-{str(season + 1)[-2:]}'"
            )
        )
        db_ex.commit()

        df.to_pandas().to_sql(
            'league_game_schedule', self.db_con, schema='nba', index=False, if_exists='append'
        )
        print('nba.historical_game_schedule has been updated\n\n')

    def get_next_game_schedule(self):
        request = requests.get('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json')
        key_dates = pl.read_database('SELECT * FROM nba.key_dates', self.db_con)
        col_order = pl.read_database(
            "SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order",
            self.db_con,
        )['column_name'].to_list()

        # Remove games already played this season - This assumes update_past_game_schedule is run first
        df_played_games = pl.read_database(
            f"SELECT * FROM nba.league_game_schedule WHERE season = '{self.cur_season}' AND team_winner IS NOT NULL",
            self.db_con,
        )

        df = []
        for game_date in request.json()['leagueSchedule']['gameDates']:
            for game in game_date['games']:
                df.append(
                    {
                        'game_id': int(game['gameId']),
                        'game_date': dateutil.parser.parse(game_date['gameDate']).date(),
                        'matchup': game['homeTeam']['teamTricode']
                        + ' vs. '
                        + game['awayTeam']['teamTricode'],
                    }
                )

        df = (
            pl.DataFrame(df)
            .with_columns(
                [
                    pl.lit(self.cur_season).alias('season'),
                    pl.lit(None).alias('team_winner'),
                    pl.lit(None).alias('team_loser'),
                ]
            )
            .join_where(
                key_dates,
                pl.col('game_date') >= pl.col('begin_date'),
                pl.col('game_date') <= pl.col('end_date'),
            )
            .select(col_order)
            .unique()
            .join(
                df_played_games.select('game_id').with_columns(pl.col('game_id').cast(pl.Int64)),
                on='game_id',
                how='anti',
            )
        )

        # Need to consider when IN-Season tourney games / All star games are added to schedule

        # Write to database
        df.to_pandas().to_sql(
            'league_game_schedule', self.db_con, schema='nba', index=False, if_exists='append'
        )
        print('nba.current_game_schedule has been updated\n\n')

    def get_team_roster(self):
        col_order = pl.read_database(
            "SELECT column_name FROM util.table_column_order WHERE table_name = 'team_roster' ORDER BY column_order",
            self.db_con,
        )['column_name'].to_list()
        teams = self.nba_teams['id'].to_list()

        print('\n--------------------- nba.team_roster')
        dfs = []
        for team in teams:
            common_teamroster = nba_ep.commonteamroster.CommonTeamRoster(
                season=self.cur_season_year, team_id=team
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
                    pl.lit(self.cur_season).alias('season'),
                    pl.lit(None).cast(pl.Float64).alias('salary'),
                    pl.lit(None).cast(pl.Date).alias('movement_date'),
                ]
            )
            .join(self.nba_teams, left_on='teamid', right_on='id', how='left')
            .rename({'teamid': 'team_id', 'abbreviation': 'team_slug'})
            .select(col_order)
        )

        # CONTROL FOR PLAYERS BEING TRADED
        # df_t = read_sql(f"SELECT * FROM nba.team_roster WHERE season = '{self.cur_season}'", db_con)
        # df_t = df_t.drop('salary', axis='columns')
        # df = concat([df, df_t])
        # df = df[~df.duplicated(keep = False)].reset_index(drop=True)

        # Write to database
        df.to_pandas().to_sql(
            'team_roster', self.db_con, schema='nba', index=False, if_exists='append'
        )
        print('nba.team_roster has been updated\n\n')

    def _fty_con(self):
        """Create connection object to fanstasy api"""

        df_leagues = pl.read_database(
            f"SELECT platform, league_id FROM fty.league WHERE season = '{self.cur_season}'",
            self.db_con,
        )

        parser = configparser.ConfigParser()
        parser.read(os.getcwd() + '/database.ini')

        fty_con = {}
        for row in df_leagues.iter_rows(named=True):
            fty_creds = dict(parser.items(row['platform'].lower() + '_api'))
            fty_creds['league_id'] = row['league_id']

            if row['platform'] == 'ESPN':
                fty_creds['year'] = str(self.cur_season_year + 1)

                fty_con['ESPN;' + str(row['league_id'])] = bb.League(
                    league_id=int(fty_creds['league_id']),
                    year=int(fty_creds['year']),
                    espn_s2=fty_creds['espn_s2'],
                    swid=fty_creds['swid'],
                )

            elif row['platform'] == 'Yahoo':
                fty_creds['token_time'] = float(fty_creds['token_time'])

                fty_con['Yahoo;' + str(row['league_id'])] = yfpy(
                    league_id=fty_creds['league_id'],
                    game_code='nba',
                    yahoo_access_token_json=fty_creds,
                )

                # Set game_id attribute
                fty_con['Yahoo;' + str(row['league_id'])].game_id = int(
                    fty_con['Yahoo;' + str(row['league_id'])].get_league_key(self.cur_season_year)[
                        0:3
                    ]
                )

        return fty_con

    def fty_get_free_agents(self):
        # Delete from database
        db_ex = self.db_con.connect()
        db_ex.execute(sqlalchemy.sql.text('TRUNCATE TABLE fty.free_agents'))
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.free_agents')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_free_agents(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_free_agents(self.fty_con[con]))

        # Write to database
        pl.concat(dfs).to_pandas().to_sql(
            'free_agents', self.db_con, schema='fty', index=False, if_exists='append'
        )
        print('fty.free_agents has been updated\n\n')

    def _espn_get_free_agents(self, espn_con):
        dfs = []
        for free_agent in espn_con.free_agents(size=1000):
            dfs.append(
                {
                    'season': self.cur_season,
                    'platform': 'ESPN',
                    'league_id': espn_con.league_id,
                    'timestamp': dt.datetime.now(zoneinfo.ZoneInfo('UTC')),
                    'player_id': free_agent.playerId,
                    'player_name': free_agent.name,
                    'player_team': free_agent.proTeam.replace('PHL', 'PHI').replace('PHO', 'PHX'),
                    'player_injury_status': None
                    if len(free_agent.injuryStatus) == 0
                    else free_agent.injuryStatus,
                    'player_position': free_agent.position,
                }
            )

        return pl.DataFrame(dfs)

    def _yahoo_get_free_agents(self, yahoo_con):
        dfs = []
        for player in yahoo_con.get_league_players():
            p_ownership = yahoo_con.get_player_ownership(player.player_key)
            if p_ownership.ownership.ownership_type in ['freeagents', 'waivers']:
                dfs.append(
                    {
                        'season': self.cur_season,
                        'platform': 'Yahoo',
                        'league_id': yahoo_con.league_id,
                        # 'timestamp': # insert afterwards
                        'player_id': p_ownership.player_id,
                        'player_name': p_ownership.name.full,
                        'player_team': p_ownership.editorial_team_abbr,
                        'player_injury_status': player.status,
                        'player_position': p_ownership.display_position,
                    }
                )
                time.sleep(1)

        return (
            pl.DataFrame(dfs)
            .with_columns(pl.col('player_injury_status').str.replace('', 'ACTIVE'))
            .insert_column(
                4,
                column=pl.Series(
                    'timestamp', [dt.datetime.now(zoneinfo.ZoneInfo('UTC'))] * len(dfs)
                ),
            )
        )

    def fty_get_league_competitor(self):
        # Remove existing records from database (if any)
        db_ex = self.db_con.connect()
        db_ex.execute(
            sqlalchemy.sql.text(
                f"DELETE FROM fty.league_competitor WHERE season = '{self.cur_season}'"
            )
        )
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.league_competitor')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_league_competitor(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_league_competitor(self.fty_con[con]))

        # Write to database
        pl.concat(dfs).to_pandas().to_sql(
            'league_competitor', self.db_con, schema='fty', index=False, if_exists='append'
        )
        print('\nfty.league_competitor has been updated\n\n')

    def _espn_get_league_competitor(self, espn_con):
        dfs = []
        for competitor in espn_con.teams:
            dfs.append(
                {
                    'season': self.cur_season,
                    'platform': 'ESPN',
                    'league_id': espn_con.league_id,
                    'competitor_id': competitor.team_id,
                    'competitor_abbrev': competitor.team_abbrev,
                    'competitor_name': competitor.team_name,
                }
            )

        return pl.DataFrame(dfs)

    def _yahoo_get_league_competitor(self, yahoo_con):
        dfs = []
        for competitor in yahoo_con.get_league_teams():
            dfs.append(
                {
                    'season': self.cur_season,
                    'platform': 'Yahoo',
                    'league_id': yahoo_con.league_id,
                    'competitor_id': competitor.team_id,
                    'competitor_abbrev': competitor.managers[0].nickname,
                    'competitor_name': competitor.name.decode(),
                }
            )

        return pl.DataFrame(dfs)

    def fty_get_league_matchup(self):
        # Remove existing records from database (if any)
        db_ex = self.db_con.connect()
        db_ex.execute(
            sqlalchemy.sql.text(
                f"DELETE FROM fty.league_matchup WHERE season = '{self.cur_season}'"
            )
        )
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.league_matchup')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_league_matchup(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_league_matchup(self.fty_con[con]))

        # Write to database
        pl.concat(dfs).to_pandas().to_sql(
            'league_matchup', self.db_con, schema='fty', index=False, if_exists='append'
        )
        print('fty.league_matchup has been updated\n\n')

    def _espn_get_league_matchup(self, espn_con):
        dfs = []
        for competitor in espn_con.teams:
            for ix, opponent in enumerate(competitor.schedule):
                dfs.append(
                    {
                        'season': self.cur_season,
                        'platform': 'ESPN',
                        'league_id': espn_con.league_id,
                        'matchup_period': ix + 1,
                        'competitor_id': competitor.team_id,
                        'opponent_id': opponent.home_team.team_id
                        if competitor.team_id == opponent.away_team.team_id
                        else opponent.away_team.team_id,
                    }
                )

        return pl.DataFrame(dfs)

    # def _yahoo_get_league_matchup(self, yahoo_con):
    #     # YET TO IMPLEMENT
    #     pass

    # # THIS DOESN'T WORK
    # def fty_get_league_matchup_dates(self):

    #     # THIS DOESN'T WORK FOR FUTURE DATES
    #     # RESORT TO MANUAL DEFINITION IN DaTABSE FOR NOW

    #     # Remove existing records from database (if any)
    #     db_ex = self.db_con.connect()
    #     db_ex.execute(sqlalchemy.sql.text(f"DELETE FROM fty.league_matchup_dates WHERE season = '{self.cur_season}'"))
    #     db_ex.commit()

    #     dfs = []
    #     for con in self.fty_con:
    #         print('\n--------------------- ' + con + ' fty.league_matchup_dates')
    #         if con.startswith('ESPN'):
    #             dfs.append(self._espn_get_league_matchup_dates(self.fty_con[con]))
    #         elif con.startswith('Yahoo'):
    #             dfs.append(self._yahoo_get_league_matchup_dates(self.fty_con[con]))

    #     # Write to database
    #     concat(dfs, ignore_index=True).to_sql('league_matchup_dates', self.db_con, schema='fty', index=False, if_exists='append')
    #     print('fty.league_matchup_dates has been updated\n\n')

    # def _espn_get_league_matchup_dates(self, espn_con):

    #     nba_match_dates = []
    #     p_sch = espn_con.pro_schedule
    #     for team in p_sch:
    #         for match_day in p_sch[team]:
    #             nba_match_dates.append({
    #                 'match_day': int(match_day),
    #                 'date': dt.fromtimestamp(p_sch[team][match_day][0]['date'] / 1000).date() - dt.timedelta(days=1) # minus one day to get the conversion right
    #             })

    #     nba_match_dates = (
    #         DataFrame(nba_match_dates)
    #         .drop_duplicates()
    #         .sort_values('match_day')
    #     )

    #     espn_matchup_dates = espn_con.matchup_ids
    #     print("one")
    #     print(espn_matchup_dates)
    #     espn_matchup_dates = DataFrame([(int(mp), int(md)) for mp, days in espn_matchup_dates.items() for md in days], columns=['matchup_period', 'match_day'])
    #     espn_matchup_dates = espn_matchup_dates[espn_matchup_dates['match_day'].isin(espn_matchup_dates.groupby('matchup_period')['match_day'].agg(['min','max']).stack())]
    #     espn_matchup_dates = espn_matchup_dates.sort_values(['matchup_period', 'match_day'])
    #     espn_matchup_dates = espn_matchup_dates.merge(nba_match_dates, on = 'match_day', how = 'left')

    #     grp_min = espn_matchup_dates.groupby('matchup_period')['match_day'].transform('min')
    #     grp_max = espn_matchup_dates.groupby('matchup_period')['match_day'].transform('max')

    #     espn_matchup_dates['from_to'] = None
    #     espn_matchup_dates.loc[espn_matchup_dates['match_day'] == grp_min, 'from_to'] = 'matchup_start'
    #     espn_matchup_dates.loc[espn_matchup_dates['match_day'] == grp_max, 'from_to'] = 'matchup_end'

    #     return (
    #         espn_matchup_dates
    #         .pivot(index='matchup_period', columns='from_to', values='date')
    #         .rename_axis(columns=None)
    #         .reset_index()
    #         .assign(season = self.cur_season, platform = 'ESPN', league_id = espn_con.league_id)
    #     )

    # def _yahoo_get_league_matchup_dates(self, yahoo_con):
    #     # YET TO IMPLEMENT
    #     pass

    def fty_get_competitor_roster(self):
        # Schedule NZT:
        # 3am
        # 8am - delete 3am records
        # 11am - delete 8am records
        # 1pm - delete 11am records
        # 3pm - delete 1pm records
        # 5pm - don't delete records, assign to next day
        # 8pm - delete 5pm records, assign to next day
        # 11pm - 'delete 8pm records, assign to next day
        col_order = pl.read_database(
            "SELECT * FROM util.table_column_order WHERE table_name = 'competitor_roster'",
            self.db_con,
        )
        assigned_date = dt.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()
        df_mup = pl.read_database(
            f"SELECT * FROM fty.league_matchup_date WHERE '{assigned_date}' BETWEEN matchup_start AND matchup_end ORDER BY table_column_order",
            self.db_con,
        )

        # Remove existing records from database (if any)
        db_ex = self.db_con.connect()
        db_ex.execute(
            sqlalchemy.sql.text(
                f"DELETE FROM fty.competitor_roster WHERE assigned_date = '{assigned_date}'"
            )
        )
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.competitor_roster')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_competitor_roster(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_competitor_roster(self.fty_con[con]))

        df = (
            pl.concat(dfs)
            .with_columns(pl.lit(assigned_date).alias('assigned_date'))
            .join(df_mup, on=['platform', 'league_id'], how='left')
            .select(col_order)
        )

        # Write to database
        df.to_pandas().to_sql(
            'competitor_roster', self.db_con, schema='fty', index=False, if_exists='append'
        )
        print('fty.competitor_roster has been updated\n\n')

    def _espn_get_competitor_roster(self, espn_con):
        dfs = []
        for competitor in espn_con.teams:
            for player in competitor.roster:
                dfs.append(
                    {
                        'season': self.cur_season,
                        'platform': 'ESPN',
                        'league_id': espn_con.league_id,
                        'timestamp': dt.datetime.now(zoneinfo.ZoneInfo('UTC')),
                        'matchup_period': espn_con.currentMatchupPeriod,
                        'competitor_id': competitor.team_id,
                        'player_fantasy_id': player.playerId,
                        'player_name': player.name,
                        'player_team': player.proTeam.replace('PHL', 'PHI').replace('PHO', 'PHX'),
                        'player_injury_status': player.injuryStatus,
                        'player_acquisition_type': player.acquisitionType,
                    }
                )

        return pl.DataFrame(dfs)

    def _yahoo_get_competitor_roster(self, yahoo_con):
        dfs = []
        for team_id in [team.team_id for team in yahoo_con.get_league_teams()]:
            for player in yahoo_con.get_team_roster_by_week(team_id).clean_data_dict()['players']:
                if player['player'].selected_position.position is not None:
                    dfs.append(
                        {
                            'season': self.cur_season,
                            'platform': 'Yahoo',
                            'league_id': yahoo_con.league_id,
                            'matchup_period': yahoo_con.get_league_info().current_week,
                            'competitor_id': team_id,
                            'player_fantasy_id': player['player'].player_id,
                            'player_name': player['player'].name.full,
                            'player_team': player['player'].editorial_team_abbr,
                            'player_injury_status': player['player'].status,
                            'player_acquisition_type': None,
                        }
                    )

        return (
            pl.DataFrame(dfs)
            .with_columns(pl.col('player_injury_status').str.replace('', 'ACTIVE'))
            .insert_column(
                4,
                column=pl.Series(
                    'timestamp', [dt.datetime.now(zoneinfo.ZoneInfo('UTC'))] * len(dfs)
                ),
            )
        )

    def fty_get_recent_activity(self):
        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.recent_activity')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_recent_activity(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_recent_activity(self.fty_con[con]))

        # Write to database
        pl.concat(dfs).to_pandas().to_sql(
            'recent_activity', self.db_con, schema='fty', index=False, if_exists='append'
        )
        print('fty.recent_activity has been updated\n\n')

    def _espn_get_recent_activity(self, espn_con):
        dfs = []
        for activity in espn_con.recent_activity(size=50):
            for action in activity.actions:
                dfs.append(
                    {
                        'season': self.cur_season,
                        'platform': 'ESPN',
                        'league_id': espn_con.league_id,
                        'timestamp': dt.fromtimestamp(activity.date / 1000),
                        'competitor_id': action[0].team_id,
                        'action': action[1],
                        'player': action[2],
                    }
                )

        df_already_done = pl.read_database(
            f"SELECT * FROM fty.recent_activity WHERE season = '{self.cur_season}' AND platform = 'ESPN' AND league_id = {espn_con.league_id}",
            self.db_con,
        )
        return pl.DataFrame(dfs).join(df_already_done, on=df_already_done.columns, how='anti')

    # def _yahoo_get_recent_activity(self, yahoo_con):

    #     df = []
    #     for activity in yahoo_con.get_league_transactions():
    #         if activity.type != 'commish':
    #             for player in activity.players:
    #                 el_id = [el for el in player.clean_data_dict()['transaction_data'].keys() if el.endswith('_team_key')][0]

    #                 df.append({
    #                     'season': self.cur_season,
    #                     'platform': 'Yahoo',
    #                     'league_id': yahoo_con.league_id,
    #                     'timestamp': dt.fromtimestamp(activity.timestamp),
    #                     'competitor_id': int(player.clean_data_dict()['transaction_data'][el_id].replace('454.l.121793.t.', '')),
    #                     'action': player.clean_data_dict()['transaction_data']['type'],
    #                     'player': player.clean_data_dict()['name']['full']
    #                 })

    #     df_t = read_sql(f"SELECT * FROM fty.recent_activity WHERE season = '{self.cur_season}' AND platform = 'Yahoo' AND league_id = {yahoo_con.league_id}", self.db_con)
    #     df = DataFrame(df).merge(df_t, how='outer', indicator=True)
    #     return df[(df._merge=='left_only')].drop('_merge', axis=1)

    # def fty_get_matchup_box_score(self):

    #     # Keep ingestion as league specific because they can have different matchup periods
    #     for con in self.fty_con:
    #         print('\n--------------------- ' + con + ' fty.matchup_box_score')
    #         if con.startswith('ESPN'):
    #             df = self._espn_get_matchup_box_score(self.fty_con[con])
    #         elif con.startswith('Yahoo'):
    #             df = self._yahoo_get_matchup_box_score(self.fty_con[con])

    #         # Delete from database
    #         db_ex = self.db_con.connect()
    #         db_ex.execute(sqlalchemy.sql.text(f"DELETE FROM fty.matchup_box_score WHERE season = '{self.cur_season}' AND platform = '{con.split(';')[0]}' AND league_id = {con.split(';')[1]} AND matchup = {df['matchup'][0]}"))
    #         db_ex.commit()

    #         # Write to database
    #         df.to_sql('matchup_box_score', self.db_con, schema='fty', index=False, if_exists='append')
    #         print(con + ' fty.matchup_box_score has been updated\n\n')

    # def _espn_get_matchup_box_score(self, espn_con):

    #     box_scores = espn_con.box_scores(matchup_period = espn_con.currentMatchupPeriod)
    #     league_cats = read_sql(f"SELECT * FROM fty.league_categories WHERE platform = 'ESPN' AND season = '{self.cur_season}' AND league_id = {espn_con.league_id}", self.db_con)
    #     stats = league_cats['category']

    #     df = []
    #     for matchup in box_scores:
    #         for h_a in ['home', 'away']:
    #             competitor = getattr(matchup, h_a + '_team')
    #             competitor_stats = getattr(matchup, h_a + '_stats')

    #             if competitor != 0:
    #                 df.append({
    #                     ** {
    #                         'season': self.cur_season,
    #                         'platform': 'ESPN',
    #                         'league_id': espn_con.league_id,
    #                         'competitor_id': competitor.team_id,
    #                         'matchup': espn_con.currentMatchupPeriod
    #                     } ,
    #                     ** dict(zip(stats, [competitor_stats[stat]['value'] for stat in stats]))
    #                 })

    #     cat_labels = (
    #         league_cats
    #         .merge(
    #             read_sql("SELECT * FROM fty.category_label", self.db_con),
    #             how='left',
    #             left_on='category',
    #             right_on='fty_category'
    #         )
    #         .set_index('fty_category')['nba_category']
    #         .to_dict()
    #     )

    #     return DataFrame(df).rename(cat_labels, axis='columns')

    # def _yahoo_get_matchup_box_score(self, yahoo_con):
    #     # TRED WITH CAUTION: still need to configure for non-conventional categories

    #     qry = f"""
    #         SELECT
    #         	ls.season,
    #         	ls.platform,
    #         	ls.league_id,
    #         	ls.week AS matchup,
    #         	id.yahoo_id,
    #             gs.game_date,
    #             gs.game_id,
    #         	bs.pts,
    #         	bs.blk,
    #         	bs.stl,
    #         	bs.ast,
    #         	bs.reb,
    #         	bs.tov,
    #         	bs.fgm,
    #         	bs.fga,
    #         	bs.ftm,
    #         	bs.fta,
    #         	bs.fg3_m
    #         FROM nba.player_box_score AS bs
    #         LEFT JOIN nba.league_game_Schedule AS gs ON bs.game_id = gs.game_id
    #         LEFT JOIN util.nba_fty_name_match AS id ON bs.player_id = id.nba_id
    #         INNER JOIN (
    #         	SELECT DISTINCT
    #         		season,
    #         		platform,
    #         		league_id,
    #         		week,
    #         		week_start,
    #         		week_end
    #         	FROM fty.league_schedule
    #         	WHERE platform = 'Yahoo'
    #         		AND season = '{self.cur_season}'
    #         		AND league_id = {yahoo_con.league_id}
    #                 AND '{self.cur_date_est}' BETWEEN week_start AND week_end
    #         ) AS ls ON gs.game_date BETWEEN ls.week_start AND ls.week_end
    #     """

    #     box_scores = read_sql(qry, self.db_con)
    #     box_scores['game_date'] = to_datetime(box_scores['game_date'])

    #     df = []
    #     for competitor in yahoo_con.get_league_teams():
    #         for dt in date_range(box_scores['game_date'].min(), box_scores['game_date'].max()):
    #             for player in yahoo_con.get_team_roster_player_info_by_date(competitor.team_id, dt):
    #                 if player.selected_position.position not in ['IL+', 'BN']:
    #                     df.append({'competitor_id': competitor.team_id, 'game_date': dt, 'yahoo_id': player.player_id})

    #     return (
    #         DataFrame(df)
    #         .merge(box_scores, on=['yahoo_id', 'game_date'], how='inner')
    #         .drop(['yahoo_id', 'game_date', 'game_id'], axis='columns')
    #         .groupby(by=['season', 'platform', 'league_id', 'competitor_id', 'matchup'], as_index=False)
    #         .sum()
    #         .assign(
    #             fg_pct = lambda x: x['fgm'] / x['fga'],
    #             ft_pct = lambda x: x['ftm'] / x['fta']
    #         )
    #     )
