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
import nbainjuries
import nba_api.stats.endpoints as nba_ep
from nba_api.stats.static import teams, players
import nba_api.stats.library.parameters as nba_parameters
import espn_api.basketball as bb
from yfpy.query import YahooFantasySportsQuery as yfpy


# Constants
timeout = 3 * 60  # 5 minute timeout


class dataHub:
    def __init__(self, platform):
        # Scalars
        self.cur_season = nba_parameters.Season.current_season
        self.cur_season_year = int(nba_parameters.Season.current_season[0:4])
        self.prev_season = nba_parameters.Season.previous_season
        self.prev_season_year = int(nba_parameters.Season.previous_season[0:4])
        self.date_est = dt.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()
        self.timestamp_utc = dt.datetime.now(zoneinfo.ZoneInfo('UTC'))
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
            .with_columns(pl.col('height').str.split('-'))
            .with_columns(
                [
                    pl.lit(self.cur_season).alias('season'),
                    (pl.col('weight').cast(pl.Float64, strict=False) / 2.2046)
                    .round(3)
                    .alias('weight_kg'),
                    (
                        (
                            pl.col('height').list.get(0).cast(pl.Float64) * 12
                            + pl.col('height').list.get(1).cast(pl.Float64)
                        )
                        * 2.54
                    )
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

    def get_team_injuries(self, force_date=None):

        dt_est = self.date_est if force_date is None else force_date
        col_order = pl.read_database(
            "SELECT column_name FROM util.table_column_order WHERE table_name = 'injuries' ORDER BY column_order",
            self.db_con,
        )['column_name'].to_list()

        # Data objects used to reconcile and complimet injury date
        teams_true = pl.read_database(
            "SELECT CONCAT(team_long, ' ', team_name) AS team, team_slug FROM nba.teams",
            self.db_con,
        )

        game_ids = pl.read_database(
            f"SELECT game_date, game_id, matchup FROM nba.league_game_schedule WHERE game_date BETWEEN '{dt_est}' AND '{dt_est + dt.timedelta(days=2)}' AND matchup LIKE '%@%'",
            self.db_con,
        )

        player_ids = pl.read_database(
            'SELECT nba_name, nba_id FROM util.nba_fty_name_match', self.db_con
        ).with_columns(
            pl.col('nba_name').str.normalize('NFKD').str.replace_all('[^\\x00-\\x7F]', '')
        )

        dt_est = dt.datetime.combine(
            dt_est, dt.time(0, 0), tzinfo=zoneinfo.ZoneInfo('America/New_York')
        )
        times = [dt_est + dt.timedelta(minutes=(60 / 4) * i) for i in range(24 * 4)]
        times = [tm.replace(tzinfo=None) for tm in times]
        times.reverse()

        def get_valid_time():
            for tm in times:
                try:
                    nbainjuries._parser.validate_injrepurl(nbainjuries.injury.gen_url(tm))
                    return tm
                except (requests.exceptions.HTTPError, Exception) as e:
                    continue

        # clean up for ingestion
        df = (
            pl.from_pandas(nbainjuries.injury.get_reportdata(get_valid_time(), return_df=True))
            .clean_names()
            .filter(
                (pl.col('reason') != 'NOT YET SUBMITTED') & (pl.col('player_name').is_not_null())
            )
            .with_columns(pl.col('player_name').str.split(', '))
            .with_columns(
                [
                    pl.col('game_date').str.to_date(format='%m/%d/%Y'),
                    pl.col('matchup').str.replace_all('@', ' @ '),
                    (
                        pl.col('player_name').list.get(1) + ' ' + pl.col('player_name').list.get(0)
                    ).alias('player_name'),
                ]
            )
            .join(teams_true, how='left', on='team')
            .join(player_ids, how='left', left_on='player_name', right_on='nba_name')
            .join(game_ids, how='left', on=['game_date', 'matchup'])
            .rename({'current_status': 'status'})
            .select(col_order)
        )

        # Delete old records from database
        db_ex = self.db_con.connect()
        for row in df.iter_rows(named=True):
            game_date = row['game_date']
            game_id = row['game_id']
            # replace to handle single quotes if they exist
            player_name = row['player_name'].replace("'", "''")
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

    def get_team_injuries_old(self):
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

        game_ids = pl.read_database(
            f"SELECT game_date, game_id, matchup FROM nba.league_game_schedule WHERE game_date BETWEEN '{self.date_est}' AND '{self.date_est + dt.timedelta(days=2)}'",
            self.db_con,
        )

        game_ids = pl.concat(
            [
                game_ids.with_columns(pl.col('matchup').str.replace(' vs. ', '@')),
                (
                    game_ids.with_columns(
                        pl.col('matchup').str.split(' vs. ').alias('matchup')
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
            .with_columns(pl.col('Player Name').str.split(', '))
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

    def get_player_box_score(self):
        # fmt: off
        bs_max_dt = (
            pl.read_database('select max(game_date) from nba.nba_player_box_score_vw where min is not null', self.db_con)
            .item()
            .strftime('%Y-%m-%d')
        )
        game_ids = pl.read_database(f"SELECT DISTINCT game_id FROM nba.league_game_schedule WHERE game_date > '{bs_max_dt}' AND game_date <= '{self.date_est}'", self.db_con)
        cols_trad = pl.read_database("select * from util.table_column_order where table_name = 'player_box_score_traditional' order by column_order", self.db_con)
        cols_adv = pl.read_database("select * from util.table_column_order where table_name = 'player_box_score_advanced' order by column_order", self.db_con)
        # fmt: on

        print('\n--------------------- nba.player_box_score')
        dfs = []
        g_ids = game_ids.get_column('game_id').to_list()
        for game_id in g_ids:
            game_id = '00' + str(int(game_id))
            print(game_id)

            # Traditional stats
            try:
                bst = (
                    pl.from_pandas(
                        nba_ep.boxscoretraditionalv3.BoxScoreTraditionalV3(
                            game_id=game_id
                        ).get_data_frames()[0]
                    )
                    .rename(
                        dict(
                            zip(
                                cols_trad.drop_nulls()['origin_name'],
                                cols_trad.drop_nulls()['column_name'],
                            )
                        )
                    )
                    .with_columns(cs.string().replace('', None))
                    .with_columns(pl.col('game_id').cast(pl.Int64))
                    .with_columns(
                        pl.col('min').str.replace(r':.*', '').cast(pl.Int64, strict=False)
                    )
                    .with_columns(
                        (pl.col('firstName') + ' ' + pl.col('familyName')).alias('player_name')
                    )
                    .select(cols_trad['column_name'].to_list())
                )
            except Exception as e:
                print(game_id + ': ' + str(e))
                # bst = pl.DataFrame({'game_id': [game_id]}).with_columns(pl.col('game_id').cast(pl.Int64))
                break

            # Advanced stats
            try:
                bsa = (
                    pl.from_pandas(
                        nba_ep.boxscoreadvancedv3.BoxScoreAdvancedV3(
                            game_id=game_id
                        ).get_data_frames()[0]
                    )
                    .rename(
                        dict(
                            zip(
                                cols_adv.drop_nulls()['origin_name'],
                                cols_adv.drop_nulls()['column_name'],
                            )
                        )
                    )
                    .with_columns(cs.string().replace('', None))
                    .with_columns(pl.col('game_id').cast(pl.Int64))
                    .select(cols_adv['column_name'].to_list())
                )
            except Exception as e:
                print(game_id + ': ' + str(e))
                # bsa = pl.DataFrame({'game_id': [game_id]}).with_columns(pl.col('game_id').cast(pl.Int64))
                break

            dfs.append(bst.join(bsa, on=['game_id', 'player_id'], how='left'))

        pl.concat(dfs).write_database('nba.player_box_score', self.db_con, if_table_exists='append')
        print('nba.player_box_score have been updated\n\n')

    def get_team_box_score(self):
        # fmt: off
        bs_max_dt = (
            pl.read_database('select max(game_date) from nba.nba_team_box_score_vw where min is not null', self.db_con)
            .item()
            .strftime('%Y-%m-%d')
        )
        game_ids = pl.read_database(f"SELECT DISTINCT game_id FROM nba.league_game_schedule WHERE game_date > '{bs_max_dt}' AND game_date <= '{self.date_est}'", self.db_con)
        cols_trad = pl.read_database("select * from util.table_column_order where table_name = 'team_box_score_traditional' order by column_order", self.db_con)
        cols_adv = pl.read_database("select * from util.table_column_order where table_name = 'team_box_score_advanced' order by column_order", self.db_con)
        # fmt: on

        print('\n--------------------- nba.team_box_score')
        dfs = []
        g_ids = game_ids.get_column('game_id').to_list()
        for game_id in g_ids:
            game_id = '00' + str(int(game_id))
            print(game_id)

            # Traditional stats
            try:
                bst = (
                    pl.from_pandas(
                        nba_ep.boxscoretraditionalv3.BoxScoreTraditionalV3(
                            game_id=game_id
                        ).get_data_frames()[1]
                    )
                    .rename(
                        dict(
                            zip(
                                cols_trad.drop_nulls()['origin_name'],
                                cols_trad.drop_nulls()['column_name'],
                            )
                        )
                    )
                    .with_columns(cs.string().replace('', None))
                    .with_columns(pl.col('game_id').cast(pl.Int64))
                    .with_columns(
                        pl.col('min').str.replace(r':.*', '').cast(pl.Int64, strict=False)
                    )
                    .group_by(['game_id', 'team_id', 'team_abbreviation'])
                    .agg(cs.numeric().sum())
                    .with_columns(
                        [
                            (pl.col('fgm') / pl.col('fga')).alias('fg_pct'),
                            (pl.col('fg3_m') / pl.col('fg3_a')).alias('fg3_pct'),
                            (pl.col('ftm') / pl.col('fta')).alias('ft_pct'),
                        ]
                    )
                )

                bst = (
                    bst.join_where(
                        bst.select('game_id', 'team_id', 'pts'),
                        pl.col('game_id') == pl.col('game_id_t'),
                        pl.col('team_id') != pl.col('team_id_t'),
                        suffix='_t',
                    )
                    .with_columns((pl.col('pts') - pl.col('pts_t')).alias('plus_minus'))
                    .select(cols_trad['column_name'].to_list())
                )

            except Exception as e:
                print(game_id + ': ' + str(e))
                # bst = pl.DataFrame({'game_id': [game_id]}).with_columns(pl.col('game_id').cast(pl.Int64))
                break

            # Advanced stats
            try:
                bsa = (
                    pl.from_pandas(
                        nba_ep.boxscoreadvancedv3.BoxScoreAdvancedV3(
                            game_id=game_id
                        ).get_data_frames()[1]
                    )
                    .rename(
                        dict(
                            zip(
                                cols_adv.drop_nulls()['origin_name'],
                                cols_adv.drop_nulls()['column_name'],
                            )
                        )
                    )
                    .with_columns(cs.string().replace('', None))
                    .with_columns(pl.col('game_id').cast(pl.Int64))
                    .select(cols_adv['column_name'].to_list())
                )
            except Exception as e:
                print(game_id + ': ' + str(e))
                # bsa = pl.DataFrame({'game_id': [game_id]}).with_columns(pl.col('game_id').cast(pl.Int64))
                break

            dfs.append(bst.join(bsa, on=['game_id', 'team_id'], how='left'))

        pl.concat(dfs).write_database('nba.team_box_score', self.db_con, if_table_exists='append')
        print('nba.team_box_score have been updated\n\n')

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
            pl.concat([df for df in dfs if len(df) > 0])
            .clean_names()
            .with_columns(
                [
                    pl.col('game_id').cast(pl.Int64),
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
                    (
                        pl.when(pl.col('wl') == 'W')
                        .then(pl.col('team_abbreviation'))
                        .otherwise(pl.col('opponent'))
                        .alias('team_winner')
                    ),
                    (
                        pl.when(pl.col('wl') == 'L')
                        .then(pl.col('team_abbreviation'))
                        .otherwise(pl.col('opponent'))
                        .alias('team_loser')
                    ),
                    (
                        pl.when(pl.col('matchup').str.contains('vs.'))
                        .then(pl.lit(True))
                        .otherwise(pl.lit(False))
                        .alias('home')
                    ),
                ]
            )
            .rename({'team_abbreviation': 'team'})
            .select(col_order)
        )

        db_ex = self.db_con.connect()
        db_ex.execute(
            sqlalchemy.sql.text(
                f"DELETE FROM nba.league_game_schedule WHERE season = '{self.cur_season}'"
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

        dfs = []
        for game_date in request.json()['leagueSchedule']['gameDates']:
            for game in game_date['games']:
                dfs.append(
                    {
                        'game_id': int(game['gameId']),
                        'game_date': dateutil.parser.parse(game_date['gameDate']).date(),
                        'matchup': game['homeTeam']['teamTricode']
                        + ' vs. '
                        + game['awayTeam']['teamTricode'],
                    }
                )

        df = (
            pl.concat(
                [
                    pl.DataFrame(dfs),
                    (
                        pl.DataFrame(dfs)
                        .with_columns(pl.col('matchup').str.split_exact(' ', n=2))
                        .unnest(pl.col('matchup'))
                        .with_columns(
                            (pl.col('field_2') + ' @ ' + pl.col('field_0'))
                            .str.strip_chars()
                            .alias('matchup')
                        )
                        .drop(cs.starts_with('field'))
                    ),
                ]
            )
            .with_columns(pl.col('matchup').str.split_exact(' ', n=2).alias('temp'))
            .unnest(pl.col('temp'))
            .with_columns(
                [
                    pl.lit(self.cur_season).alias('season'),
                    pl.lit(None).alias('team_winner'),
                    pl.lit(None).alias('team_loser'),
                    pl.col('field_0').alias('team'),
                    pl.col('field_2').alias('opponent'),
                    pl.when(pl.col('field_1') == 'vs.')
                    .then(pl.lit(True))
                    .otherwise(pl.lit(False))
                    .alias('home'),
                ]
            )
            .with_columns(
                [
                    pl.when(pl.col('matchup').str.strip_chars().is_in(['@', 'vs.']))
                    .then(pl.lit('undetermined') if col == 'matchup' else pl.lit(None))
                    .otherwise(pl.col(col))
                    .alias(col)
                    for col in ['team', 'opponent', 'matchup']
                ]
            )
            .join_where(
                key_dates,
                pl.col('game_date') >= pl.col('begin_date'),
                pl.col('game_date') <= pl.col('end_date'),
            )
            .select(col_order)
            .join(
                df_played_games.select('game_id').with_columns(pl.col('game_id').cast(pl.Int64)),
                on='game_id',
                how='anti',
            )
            .filter(
                pl.col('team').is_in(self.nba_teams.get_column('abbreviation').to_list())
                | pl.col('opponent').is_in(self.nba_teams.get_column('abbreviation').to_list())
                | (pl.col('matchup') == 'undetermined')
            )
        )

        # Write to database
        df.to_pandas().to_sql(
            'league_game_schedule', self.db_con, schema='nba', index=False, if_exists='append'
        )
        print('nba.current_game_schedule has been updated\n\n')

    def get_team_roster(self, pre_season=False):
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
                    pl.lit(None if pre_season else self.date_est).cast(pl.Date).alias('entry_date'),
                    pl.lit(None).cast(pl.Date).alias('exit_date'),
                ]
            )
            .join(self.nba_teams, left_on='teamid', right_on='id', how='left')
            .rename({'teamid': 'team_id', 'abbreviation': 'team_slug'})
            .select(col_order)
        )

        # Write to database depending on situation
        if pre_season:
            df.to_pandas().to_sql(
                'team_roster', self.db_con, schema='nba', index=False, if_exists='append'
            )
            print('nba.team_roster has been updated\n\n')
        else:
            df_existing = pl.read_database(
                f"SELECT * FROM nba.team_roster WHERE season = '{self.cur_season}' AND exit_date IS NULL",
                self.db_con,
                schema_overrides={
                    'team_id': pl.Int64,
                    'player_id': pl.Int64,
                    'entry_date': pl.Date,
                    'exit_date': pl.Date,
                },
            ).with_columns(
                pl.when(pl.col('exit_date').is_null())
                .then(pl.lit(self.date_est))
                .otherwise(pl.col('exit_date'))
                .alias('exit_date')
            )

            df_traded = (
                pl.concat([df, df_existing])
                .join(
                    (
                        df.join(
                            df_existing, on=['season', 'team_id', 'player_id'], how='anti'
                        ).select('player_id')
                    ),
                    on='player_id',
                    how='inner',
                )
                .with_columns(pl.col('salary').backward_fill().forward_fill().over('player_id'))
            )

            if len(df_traded) > 0:
                del_ids = df_traded.unique('player_id')['player_id'].to_list()
                del_ids = ', '.join(map(str, del_ids))

                # Delete old records from database
                db_ex = self.db_con.connect()
                db_ex.execute(
                    sqlalchemy.sql.text(
                        f"DELETE FROM nba.team_roster WHERE season = '{self.cur_season}' AND player_id IN ({del_ids}) AND exit_date IS NULL"
                    )
                )
                db_ex.commit()

                df_traded.to_pandas().to_sql(
                    'team_roster', self.db_con, schema='nba', index=False, if_exists='append'
                )
                print('nba.team_roster traded players have been updated\n\n')
            else:
                print('nba.team_roster: nothing to update\n\n')

    def _fty_con(self):
        """Create connection object to fanstasy api"""

        df_leagues = pl.read_database(
            f"""
                SELECT lgl.platform, lgl.league_id, lgl_end.league_end_date
                FROM fty.league AS lgl
                LEFT JOIN (
                    SELECT league_id, MAX(matchup_end) AS league_end_date
                    FROM fty.league_matchup_dates
                    WHERE season = '{self.cur_season}'
                    GROUP BY league_id
                ) AS lgl_end ON lgl.league_id = lgl_end.league_id
                WHERE lgl.season = '{self.cur_season}'
                    AND (lgl_end.league_end_date + 1) >= '{self.date_est}'
            """,
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
                    'timestamp': self.timestamp_utc,
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
                column=pl.Series('timestamp', [self.timestamp_utc] * len(dfs)),
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

        df_byes = pl.read_database(
            f"SELECT * FROM fty.league_byes WHERE platform = 'ESPN' AND season = '{self.cur_season}' AND league_id = {espn_con.league_id}",
            self.db_con,
        )

        dfs = []
        for competitor in espn_con.teams:
            if competitor.team_id in df_byes['competitor_id'].to_list():
                bye_periods = (
                    df_byes.filter(pl.col('competitor_id') == competitor.team_id)
                    .get_column('matchup_period')
                    .to_list()
                )

                for ix in bye_periods:
                    competitor.schedule.insert(ix - 1, None)

            for ix, opponent in enumerate(competitor.schedule):
                dfs.append(
                    {
                        'season': self.cur_season,
                        'platform': 'ESPN',
                        'league_id': espn_con.league_id,
                        'matchup_period': ix + 1,
                        'competitor_id': competitor.team_id,
                        'opponent_id': opponent.home_team.team_id
                        if opponent and competitor.team_id == opponent.away_team.team_id
                        else (opponent.away_team.team_id if opponent else None),
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
            "SELECT * FROM util.table_column_order WHERE table_name = 'competitor_roster' ORDER BY table_column_order",
            self.db_con,
        )['column_name'].to_list()

        df_mup = pl.read_database(
            f"SELECT * FROM fty.league_matchup_dates WHERE '{self.date_est}' BETWEEN matchup_start AND matchup_end",
            self.db_con,
        )

        # Remove existing records from database (if any)
        db_ex = self.db_con.connect()
        db_ex.execute(
            sqlalchemy.sql.text(
                f"DELETE FROM fty.competitor_roster WHERE assigned_date = '{self.date_est}'"
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
            .with_columns(pl.lit(self.date_est).alias('assigned_date'))
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
                        'timestamp': self.timestamp_utc,
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
                column=pl.Series('timestamp', [self.timestamp_utc] * len(dfs)),
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
                        'timestamp': dt.datetime.fromtimestamp(
                            activity.date / 1000, tz=dt.timezone.utc
                        ),
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

    def _yahoo_get_recent_activity(self, yahoo_con):
        dfs = []
        for activity in yahoo_con.get_league_transactions():
            if activity.type != 'commish':
                for player in activity.players:
                    el_id = [
                        el
                        for el in player.clean_data_dict()['transaction_data'].keys()
                        if el.endswith('_team_key')
                    ][0]

                    dfs.append(
                        {
                            'season': self.cur_season,
                            'platform': 'Yahoo',
                            'league_id': yahoo_con.league_id,
                            'timestamp': dt.fromtimestamp(activity.timestamp),
                            'competitor_id': int(
                                player.clean_data_dict()['transaction_data'][el_id].replace(
                                    '454.l.121793.t.', ''
                                )
                            ),
                            'action': player.clean_data_dict()['transaction_data']['type'],
                            'player': player.clean_data_dict()['name']['full'],
                        }
                    )

        df_t = pl.read_database(
            f"SELECT * FROM fty.recent_activity WHERE season = '{self.cur_season}' AND platform = 'Yahoo' AND league_id = {yahoo_con.league_id}",
            self.db_con,
        )
        return pl.DataFrame(dfs).join(df_t, on=df_t.columns, how='anti')

    def fty_get_matchup_box_score(self):
        # Keep ingestion as league specific because they can have different matchup periods
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.matchup_box_score')
            if con.startswith('ESPN'):
                df = self._espn_get_matchup_box_score(self.fty_con[con])
            elif con.startswith('Yahoo'):
                df = self._yahoo_get_matchup_box_score(self.fty_con[con])

            # Delete from database
            db_ex = self.db_con.connect()
            db_ex.execute(
                sqlalchemy.sql.text(
                    f"DELETE FROM fty.matchup_box_score WHERE season = '{self.cur_season}' AND platform = '{con.split(';')[0]}' AND league_id = {con.split(';')[1]} AND matchup = {df['matchup'][0]}"
                )
            )
            db_ex.commit()

            # Write to database
            df.to_pandas().to_sql(
                'matchup_box_score', self.db_con, schema='fty', index=False, if_exists='append'
            )
            print(con + ' fty.matchup_box_score has been updated\n\n')

    def _espn_get_matchup_box_score(self, espn_con):
        box_scores = espn_con.box_scores(matchup_period=espn_con.currentMatchupPeriod)
        league_cats = pl.read_database(
            f"SELECT * FROM fty.league_categories WHERE platform = 'ESPN' AND season = '{self.cur_season}' AND league_id = {espn_con.league_id}",
            self.db_con,
        )
        stats = league_cats['category'].to_list()

        dfs = []
        for box_score in box_scores:
            for h_a in ['home', 'away']:
                competitor = getattr(box_score, h_a + '_team')
                competitor_stats = getattr(box_score, h_a + '_stats')

                if competitor != 0:
                    dfs.append(
                        {
                            **{
                                'season': self.cur_season,
                                'platform': 'ESPN',
                                'league_id': espn_con.league_id,
                                'competitor_id': competitor.team_id,
                                'matchup': espn_con.currentMatchupPeriod,
                            },
                            **dict(zip(stats, [competitor_stats[stat]['value'] for stat in stats])),
                        }
                    )

        cat_labels = league_cats.join(
            pl.read_database('SELECT * FROM fty.category_label', self.db_con),
            how='left',
            left_on='category',
            right_on='fty_category',
        )

        return pl.DataFrame(dfs).rename(
            dict(zip(cat_labels['category'], cat_labels['nba_category']))
        )

    def _yahoo_get_matchup_box_score(self, yahoo_con):
        qry = f"""
            SELECT
                ls.season,
                ls.platform,
                ls.league_id,
                ls.week AS matchup,
                id.yahoo_id,
                gs.game_date,
                gs.game_id,
                bs.pts,
                bs.blk,
                bs.stl,
                bs.ast,
                bs.reb,
                bs.tov,
                bs.fgm,
                bs.fga,
                bs.ftm,
                bs.fta,
                bs.fg3_m
            FROM nba.player_box_score AS bs
            LEFT JOIN nba.league_game_Schedule AS gs ON bs.game_id = gs.game_id
            LEFT JOIN util.nba_fty_name_match AS id ON bs.player_id = id.nba_id
            INNER JOIN (
                SELECT DISTINCT
                    season,
                    platform,
                    league_id,
                    week,
                    week_start,
                    week_end
                FROM fty.league_schedule
                WHERE platform = 'Yahoo'
                    AND season = '{self.cur_season}'
                    AND league_id = {yahoo_con.league_id}
                    AND '{self.cur_date_est}' BETWEEN week_start AND week_end
            ) AS ls ON gs.game_date BETWEEN ls.week_start AND ls.week_end
        """

        box_scores = (
            pl.read_database(qry, self.db_con)
            # .with_columns(pl.col('game_date').cast(pl.Date)) # NOT SURE WHY NEEDED?
        )

        dfs = []
        for competitor in yahoo_con.get_league_teams():
            for date_r in pl.date_range(
                box_scores['game_date'].min(), box_scores['game_date'].max()
            ):
                for player in yahoo_con.get_team_roster_player_info_by_date(
                    competitor.team_id, date_r
                ):
                    if player.selected_position.position not in ['IL+', 'BN']:
                        dfs.append(
                            {
                                'competitor_id': competitor.team_id,
                                'game_date': date_r,
                                'yahoo_id': player.player_id,
                            }
                        )

        return (
            pl.DataFrame(dfs)
            .join(box_scores, on=['yahoo_id', 'game_date'], how='inner')
            .group_by(['season', 'platform', 'league_id', 'competitor_id', 'matchup'])
            .agg(pl.all().exclude(['yahoo_id', 'game_date', 'game_id']).sum())
            .with_columns(
                fg_pct=pl.col('fgm') / pl.col('fga'), ft_pct=pl.col('ftm') / pl.col('fta')
            )
        )

import asyncio
import concurrent.futures
import aiohttp


def _run_coro(coro):
    """
    Run a coroutine to completion, whether or not an event loop is already
    running in this thread. Plain scripts / python REPL have no running loop,
    so asyncio.run() works directly. Interactive consoles built on IPython
    (Jupyter, Positron) already have one running, which asyncio.run() refuses
    to nest inside — so in that case, run the coroutine on a separate thread
    with its own fresh loop instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # no loop running here — the normal case
        return asyncio.run(coro)

    # a loop is already running (e.g. Positron/IPython console) — hand the
    # coroutine to a new thread that starts its own loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class _StatyxClient:
    """Thin transport layer: pagination + concurrency. No knowledge of specific endpoints."""

    def __init__(self, api_key: str, max_concurrent: int = 10):
        self.api_key = api_key
        self.max_concurrent = max_concurrent
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=self.max_concurrent)
        self.session = aiohttp.ClientSession(
            connector=connector,
            headers={"x-api-key": self.api_key}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()

    async def get_paginated(self, url: str, params: dict) -> list:
        """Fetch every page of one list endpoint call."""
        rows = []
        offset = 0
        while True:
            page_params = {**params, "limit": 200, "offset": offset}
            async with self.session.get(url, params=page_params) as r:
                r.raise_for_status()
                data = (await r.json())["data"]
            rows.extend(data)
            if len(data) < 200:  # last page
                break
            offset += 200
        return rows

    async def get_one(self, url: str, params: dict) -> dict:
        """Fetch a single-object endpoint (no list, no pagination)."""
        async with self.session.get(url, params=params) as r:
            r.raise_for_status()
            return (await r.json())["data"]

    async def get_many(self, calls: list[tuple], paginated: bool = True) -> list:
        """
        Run get_paginated (or get_one, if paginated=False) concurrently across many calls.
        calls: list of (key, url, params). `key` is just a label attached to the
        result so callers can match it back up — pass None if there's no key.
        """
        fetch = self.get_paginated if paginated else self.get_one

        async def fetch_one(key, url, params):
            try:
                result = await fetch(url, params)
                return key, result, None
            except aiohttp.ClientError as e:
                return key, None, str(e)

        tasks = [fetch_one(*call) for call in calls]
        return await asyncio.gather(*tasks)


def _flatten_hit_rates(row: dict) -> list[dict]:
    """
    hit-rates responses nest per-window stats:
    {market, line, side, season, sample_size, windows: {L5: {...}, L10: {...}, ...}}
    Expand into one tidy row per window rather than one wide row per player.
    """
    base = {k: v for k, v in row.items() if k != "windows"}
    return [
        {**base, "window": window, **stats}
        for window, stats in row.get("windows", {}).items()
    ]


class StatyxPipeline:
    """Orchestrates fetch + normalize for downstream nba_mod use.

    Adding a new endpoint is a one-line addition to ENDPOINTS — no new method needed,
    unless its response needs custom flattening (see "flatten" below).
    """

    BASE_URL = "https://api.statyx.io/v1/nba"

    ENDPOINTS = {
        "game_stats":     {"path": "/players/{key}/game-stats",    "keyed": True,  "key_column": "player_id", "paginated": True,  "flatten": None},
        "shot_zones":     {"path": "/players/{key}/shot-zones",    "keyed": True,  "key_column": "player_id", "paginated": True,  "flatten": None},
        "hit_rates":      {"path": "/players/{key}/hit-rates",     "keyed": True,  "key_column": "player_id", "paginated": False, "flatten": _flatten_hit_rates},
        "advanced_stats": {"path": "/players/{key}/advanced-stats","keyed": True,  "key_column": "player_id", "paginated": True,  "flatten": None},
        "play_types":     {"path": "/players/{key}/play-types",    "keyed": True,  "key_column": "player_id", "paginated": True,  "flatten": None},
        "schedule":       {"path": "/schedule",                    "keyed": False, "key_column": None,        "paginated": True,  "flatten": None},
        "standings":      {"path": "/standings",                   "keyed": False, "key_column": None,        "paginated": True,  "flatten": None},
        "contracts":      {"path": "/contracts",                   "keyed": False, "key_column": None,        "paginated": True,  "flatten": None},
    }

    def __init__(self, max_concurrent: int = 10):
        parser = configparser.ConfigParser()
        parser.read(os.getcwd() + '/database.ini')
        api_key = dict(parser.items('statyx'))
        self.api_key = api_key['key']
        self.max_concurrent = max_concurrent
        self.errors: dict = {}

    def _url(self, endpoint: str, key=None) -> str:
        path = self.ENDPOINTS[endpoint]["path"]
        return self.BASE_URL + path.format(key=key)

    async def _fetch_keyed(self, endpoint: str, keys: list, params: dict) -> list:
        spec = self.ENDPOINTS[endpoint]
        async with _StatyxClient(self.api_key, self.max_concurrent) as client:
            calls = [(key, self._url(endpoint, key), params) for key in keys]
            return await client.get_many(calls, paginated=spec["paginated"])

    async def _fetch_single(self, endpoint: str, params: dict):
        spec = self.ENDPOINTS[endpoint]
        async with _StatyxClient(self.api_key, self.max_concurrent) as client:
            fetch = client.get_paginated if spec["paginated"] else client.get_one
            return await fetch(self._url(endpoint), params)

    def run(self, endpoint: str, params: dict | None = None, keys: list | None = None) -> pl.DataFrame:
        """
        Sync entry point.

        endpoint: name from ENDPOINTS, e.g. "game_stats"
        params:   query params, e.g. {"season": 2024}. Some endpoints (e.g. "hit_rates")
                  have required params — see ENDPOINTS / the API docs for each.
        keys:     required if the endpoint is keyed (e.g. player_ids); omit otherwise

        On return, self.errors holds any per-key failures ({key: error_message}).
        """
        if endpoint not in self.ENDPOINTS:
            raise ValueError(f"Unknown endpoint '{endpoint}'. Options: {list(self.ENDPOINTS)}")

        spec = self.ENDPOINTS[endpoint]
        params = params or {}
        self.errors = {}
        flatten = spec["flatten"]

        if spec["keyed"]:
            if not keys:
                raise ValueError(f"'{endpoint}' requires `keys` (e.g. player_ids)")

            results = _run_coro(self._fetch_keyed(endpoint, keys, params))
            key_column = spec["key_column"]

            rows = []
            for key, data, err in results:
                if err is not None:
                    self.errors[key] = err
                    continue

                # data is a list of rows if paginated, a single dict otherwise
                records = data if spec["paginated"] else [data]
                for row in records:
                    expanded = flatten(row) if flatten else [row]
                    for r in expanded:
                        rows.append({key_column: key, **r})
        else:
            data = _run_coro(self._fetch_single(endpoint, params))
            records = data if spec["paginated"] else [data]
            rows = []
            for row in records:
                rows.extend(flatten(row) if flatten else [row])

        return pl.DataFrame(rows) if rows else pl.DataFrame()