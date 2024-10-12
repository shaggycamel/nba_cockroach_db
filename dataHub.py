import configparser
import snakecase
import re
from os import getcwd
from requests import get
from datetime import datetime, date, timedelta
from dateutil.parser import parse
from pytz import timezone
from time import sleep
from pandas import DataFrame, concat, read_sql, to_datetime
from numpy import where
from sqlalchemy import create_engine
from sqlalchemy.sql import text
from pandasql import sqldf; pysqldf = lambda q: sqldf(q, locals())

from nba_api.stats.endpoints import playercareerstats, commonplayerinfo, playergamelog, leaguegamelog, commonteamroster, boxscoreadvancedv2, boxscoretraditionalv2
from nba_api.stats.static import players, teams
from nba_api.stats.library.parameters import Season
from yfpy.query import YahooFantasySportsQuery
import espn_api.basketball as bb
import pro_sports_transactions as pst

import asyncio
import nest_asyncio; nest_asyncio.apply() # needed for running code in jupyter


# Constants
timeout = 3600 + 600 # 1hour & 10mins
active_players_list = DataFrame(players.get_active_players())['id'].to_list()
nba_teams = DataFrame(teams.get_teams())


class dataHub:
    
    def __init__(self):
        self



    
    def db_connect(self, platform):
        """ Establish connection to desired platform """
        parser = configparser.ConfigParser()
        parser.read(getcwd() + '/database.ini')
        db_creds = dict(parser.items(platform))
        sql_url = 'dialect://user:password@host:port/database'
        for el in db_creds: sql_url = sql_url.replace(el, db_creds[el])

        return create_engine(sql_url, connect_args={'connect_timeout': 5 * 60}) # 5 minute timeout
        


    
    def get_player_season_stats(self, db_con):
        """ Season stats (totals) """

        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'player_season_stats' ORDER BY column_order", db_con)['column_name'].to_list()

        print('\n--------------------- player season stats')
        df = DataFrame()
        for player in active_players_list:
            player_season = playercareerstats.PlayerCareerStats(player_id=str(player), timeout=timeout)
            player_season = player_season.data_sets[0].get_data_frame()
            df = concat([df, player_season], ignore_index=True)
            ix = active_players_list.index(player)
            if ix % 50 == 0: 
                print('player:', ix, '/', len(active_players_list))
            sleep(1)
        print('player:', ix, '/', len(active_players_list))

        # Clean up for ingestion into database
        df = df.rename(snakecase.convert, axis='columns')
        df = df[col_order]

        # Combine with existing dataset & latest record per season/player
        df_t = read_sql('SELECT * FROM nba.player_season_stats', db_con)
        df = concat([df, df_t], ignore_index=True)
        df = df.sort_values(['season_id', 'player_id'], ascending=False).groupby(['season_id', 'player_id']).head(1)

        # Write to database
        df.to_sql('player_season_stats', db_con, schema='nba', index=False, if_exists='replace')
        print('player_season_stats has been updated\n\n')
        


    
    def get_player_info(self, db_con):

        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'player_info' ORDER BY column_order", db_con)['column_name'].to_list()

        print('\n--------------------- player_info')
        df = DataFrame()
        for player in active_players_list:
            player_info = commonplayerinfo.CommonPlayerInfo(player_id=str(player))
            player_info = player_info.data_sets[0].get_data_frame()
            df = concat([df, player_info], ignore_index=True)
            ix = active_players_list.index(player)
            if ix % 50 == 0: 
                print('player:', ix, '/', len(active_players_list))
            sleep(1)
        print('player:', ix, '/', len(active_players_list))

        # Clean up for ingestion into database
        df['HEIGHT'] = [None if (el is None or el == '') else el for el in df['HEIGHT']]
        df['WEIGHT'] = [None if (el is None or el == '') else el for el in df['WEIGHT']]
        df['HEIGHT_CM'] = [round((float(el[0]) * 12 + float(el[1])) * 2.54, 2) if el is not None else None for el in df['HEIGHT'].str.split('-')]
        df['WEIGHT_KG'] = [round(float(el) / 2.2046, 3) if el is not None else None for el in df['WEIGHT']]
        df = df.rename(snakecase.convert, axis='columns')
        df = df[col_order]

        df_t = read_sql('SELECT * FROM nba.player_info', db_con)
        df = concat([df, df_t], ignore_index=True)
        df = df.sort_values(['to_year', 'games_played_current_season_flag'], ascending=False).groupby('person_id').head(1)

        # Write to database
        df.to_sql('player_info', db_con, schema='nba', index=False, if_exists='replace')
        print('player_info has been updated\n\n')

    

    
    def get_box_scores(self, db_con):

        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'boxscore' ORDER BY column_order", db_con)['column_name'].to_list()
        max_game_id = (read_sql('SELECT MAX(game_id) FROM nba.player_box_score', db_con)['max'][0] + timedelta(days=1)).strftime('%m/%d/%Y')
        date_to = datetime.now(timezone('US/Eastern')).date().strftime('%m/%d/%Y')


        
        
    def get_player_game_log(self, db_con):
        # NEED TO UPDATE KEY DATES WITH LATEST DATES IN ORDER FOR SEASON TYPE TO BE CORRECT

        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'player_game_log' ORDER BY column_order", db_con)['column_name'].to_list()
        date_from = (read_sql('SELECT MAX(game_date) FROM nba.player_game_log', db_con)['max'][0] + timedelta(days=1)).strftime('%m/%d/%Y')
        date_to = datetime.now(timezone('US/Eastern')).date().strftime('%m/%d/%Y')
        season_types = read_sql("SELECT * FROM util.key_dates WHERE begin_date <= '{}' AND end_date >= '{}'".format(date_from, date_to), db_con)['season_type'].to_list()
        if 'All Star' in season_types: 
            season_types = ['All Star']

        # Connect to API and collect data
        print('\n--------------------- player_game_log')
        df = DataFrame() 
        for player in active_players_list:
            for season_type in season_types: 
                player_game_log = playergamelog.PlayerGameLog(
                    player_id=str(player), 
                    date_from_nullable=date_from, 
                    date_to_nullable=date_to,
                    season_type_all_star=season_type, 
                    timeout=timeout
                )
                player_game_log = player_game_log.data_sets[0].get_data_frame()
                player_game_log['season_type'] = season_type
                df = concat([df, player_game_log], ignore_index=True)
            ix = active_players_list.index(player)
            if ix % 50 == 0: 
                print('player:', ix, '/', len(active_players_list))
            sleep(1)
        print('player:', ix, '/', len(active_players_list))

        df['GAME_DATE'] = [parse(el).date() for el in df['GAME_DATE']]
        df['year_season'] = Season.current_season_year
        df['slug_season'] = Season.current_season
        df = df.rename(snakecase.convert, axis='columns')
        conversion_cols = ['game_id', 'player_id', 'fgm', 'fga', 'fg3_m', 'fg3_a', 'min', 'ftm', 'fta', 'oreb', 'dreb', 'reb', 'ast', 'stl', 'blk', 'tov', 'pf', 'pts', 'plus_minus', 'video_available']
        for col in conversion_cols: df[col] = df[col].astype(float)
        df = df[col_order]

        # Write to database
        df.to_sql('player_game_log', db_con, schema='nba', index=False, if_exists='append')
        print('player_game_log has been updated to:', parse(date_to).strftime('%Y-%m-%d'), '\n\n')



    
    #CREATE NEW PROC TO BRING IN TEAM BOXSCORE AND RATINGS
    def get_box_score(self, db_con):

        bs_max_dt = (
            read_sql("""
                SELECT MAX(ls.game_date) 
                FROM nba.team_box_score AS bs
                LEFT JOIN nba.league_game_schedule AS ls on bs.game_id = ls.game_id
            """, db_con)
            ['max'][0]
            .strftime('%Y-%m-%d')
        )
        
        game_ids = (
            read_sql(f"""
                SELECT game_id, game_date
                FROM nba.league_game_schedule
                WHERE game_date > '{bs_max_dt}'
                    AND game_date <= current_date
            """, db_con)
        )
        
        trad_adv_lst = ['player', 'team']
        
        for game_id in game_ids['game_id']:
            game_id = '00' + str(int(game_id))
            # print(game_id)
        
            dfs = []
            bsa = boxscoreadvancedv2.BoxScoreAdvancedV2(game_id=game_id)
            if len(bsa.get_normalized_dict()['PlayerStats']) == 0:
                continue
        
            bst = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
            
            for el in [0, 1]:
        
                bst_col_order = read_sql(f"SELECT column_name FROM util.table_column_order WHERE table_name = '{trad_adv_lst[el]}_box_score_traditional' ORDER BY column_order", db_con)['column_name'].to_list()
                bsa_col_order = read_sql(f"SELECT column_name FROM util.table_column_order WHERE table_name = '{trad_adv_lst[el]}_box_score_advanced' ORDER BY column_order", db_con)['column_name'].to_list()
                
                bst_df = (
                    bst
                    .get_data_frames()[el]
                    .rename(snakecase.convert, axis='columns')
                    .drop_duplicates()
                    .assign(game_id = lambda x: x['game_id'].astype('int'))
                    .assign(min = lambda x: [int(re.sub(r'\..*', '', el)) if el is not None else None for el in x['min']])
                    [bst_col_order]
                )
        
                bsa_df = (
                    bsa
                    .get_data_frames()[el]
                    .rename(snakecase.convert, axis='columns')
                    .drop_duplicates()
                    .assign(game_id = lambda x: x['game_id'].astype('int'))
                    [bsa_col_order]
                )
                
                jn_cols = list(set(bst_df.columns) & set(bsa_df.columns))
                df = bst_df.merge(bsa_df, how='left', on=jn_cols)
                dfs.append(df)
        
            dfs[0].to_sql('player_box_score', db_con, schema='nba', index=False, if_exists='append')
            dfs[1].to_sql('team_box_score', db_con, schema='nba', index=False, if_exists='append')

        print('player and team box_score have been updated\n\n')

        

    
    def update_past_game_schedule(self, db_con):
        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order", db_con)['column_name'].to_list()
        
        print('\n--------------------- historical_league_game_schedule')
        df = DataFrame() 
        for type_season in ['Regular Season', 'Pre Season', 'Playoffs', 'All Star']:
            hist_game_schedule = leaguegamelog.LeagueGameLog(season_type_all_star=type_season, season=Season.current_season_year-1)
            hist_game_schedule = hist_game_schedule.get_data_frames()[0]
            hist_game_schedule['type_season'] = type_season
            df = concat([df, hist_game_schedule], ignore_index=True)
            sleep(1)

        df['GAME_ID'] = df['GAME_ID'].astype(float)
        df = df.groupby(['GAME_ID']).head(1)
        df['GAME_DATE'] = [parse(el).date() for el in df['GAME_DATE']]
        df['slug_matchup'] = df['MATCHUP']
        df['opponent'] = df['MATCHUP'].str.replace(r'[ @ | vs. ]', '', regex=True)
        df['opponent'] = df.apply(lambda x: x['opponent'].replace(x['TEAM_ABBREVIATION'], ''), axis=1)
        df['slug_team_winner'] = where(df['WL'] == 'W', df['TEAM_ABBREVIATION'], df['opponent'])
        df['slug_team_loser'] = where(df['WL'] == 'L', df['TEAM_ABBREVIATION'], df['opponent'])
        df['slug_season'] = Season.previous_season
        df = df.rename(snakecase.convert, axis='columns')
        df = df[col_order]
        
        df_t = read_sql("SELECT * FROM nba.league_game_schedule WHERE slug_season != '{}'".format(Season.previous_season), db_con)
        df = concat([df_t, df], ignore_index=True).drop_duplicates()
        df.to_sql('league_game_schedule', db_con, schema='nba', index=False, if_exists='replace')
        print('historical_game_schedule has been updated\n\n')


    
    
    def get_next_game_schedule(self, db_con):
        
        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order", db_con)['column_name'].to_list()
        
        # data request
        request = get(f'https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/{Season.current_season_year}/league/00_full_schedule_week_tbds.json')
        
        # Dataframe object to be added to
        df = DataFrame()
        
        # Loop through month elements
        for month in request.json()['lscd']:
            df_row = DataFrame(month['mscd']['g'])[['gid', 'gdte', 'an', 'ac', 'htm', 'vtm', 'v', 'h']]
        
            # Obtain home and away team info
            for col in ['h', 'v']:
                df_col = DataFrame([[el['tid'], el['ta']] for el in df_row[col]])
                df_col.columns = ['home_team_id', 'home_team_slug'] if col == 'h' else ['away_team_id', 'away_team_slug']
                df_row = concat([df_row, df_col], axis = 1)
        
            # Rename columns
            df_row = df_row.drop(columns=['v', 'h'])
            df_row = df_row.rename(columns={'gid':'game_id', 'gdte':'game_date', 'an':'arena', 'ac':'city', 'htm':'home_team_time', 'vtm':'away_team_time'})
        
            # Collate data
            df = concat([df, df_row], ignore_index=True)
        
        # Cast date columns to_date & Create new columns
        df['game_date'] = [parse(el).date() for el in df['game_date']]
        df['slug_season'] = Season.current_season
        df['slug_matchup'] = df['home_team_slug'] + ' vs. ' + df['away_team_slug']
        df['slug_team_winner'] = None
        df['slug_team_loser'] = None
        
        key_dates = read_sql('SELECT * FROM util.key_dates', db_con)
        df = (
            sqldf("""
                SELECT key_dates.season_type AS type_season, df.*
                FROM df
                LEFT JOIN key_dates ON df.game_date >= key_dates.begin_date 
                    AND df.game_date <= key_dates.end_date
            """, locals())
            [col_order]
            .drop_duplicates()
        )

        # Write to database
        df.to_sql('league_game_schedule', db_con, schema='nba', index=False, if_exists='append')
        # return df
        print('current_game_schedule has been updated\n\n')



    
    def get_team_roster(self, db_con):

        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'team_roster' ORDER BY column_order", db_con)['column_name'].to_list()
        
        print('\n--------------------- commonteamroster')
        df = DataFrame()
        for team in nba_teams['id'].to_list():
            common_teamroster = commonteamroster.CommonTeamRoster(season=Season.current_season_year, team_id=team)
            common_teamroster = common_teamroster.get_data_frames()[0]
            df = concat([df, common_teamroster], ignore_index=True)
            ix = nba_teams['id'].to_list().index(team)
            if ix % 5 == 0: 
                print('team:', ix, '/', len(nba_teams['id'].to_list()))
            sleep(1)
        print('team:', ix, '/', len(nba_teams['id'].to_list()))
        
        df = df.merge(
            nba_teams[['id', 'abbreviation']].rename(columns={'id': 'TeamID', 'abbreviation': 'team_slug'}), 
            on=['TeamID'],
            how = 'left'
        )
        df['HEIGHT'] = [None if (el is None or el == '') else el for el in df['HEIGHT']]
        df['WEIGHT'] = [None if (el is None or el == '') else el for el in df['WEIGHT']]
        df['HEIGHT_CM'] = [round((float(el[0]) * 12 + float(el[1])) * 2.54, 2) if el is not None else None for el in df['HEIGHT'].str.split('-')]
        df['WEIGHT_KG'] = [round(float(el) / 2.2046, 3) if el is not None else None for el in df['WEIGHT']]
        df['NUM'] = [None if (el is None or el == '') else el for el in df['NUM']]
        df = df.rename(snakecase.convert, axis='columns')
        df['slug_season'] = Season.current_season
        df = df[col_order]

        # CONTROL FOR PLAYERS BEING TRADED
        df_t = read_sql('SELECT * FROM nba.team_roster WHERE season = {}'.format(Season.current_season_year), db_con)
        df = concat([df, df_t])
        df = df[~df.duplicated(keep = False)].reset_index(drop=True)
        
        # Write to database
        df.to_sql('team_roster', db_con, schema='nba', index=False, if_exists='append')
        print('team_roster has been updated\n\n')



    
    def get_transactions(self, db_con):

        print('\n--------------------- transactions')
        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'transaction_log' ORDER BY column_order", db_con)['column_name'].to_list()
        date_from = read_sql('SELECT MAX(date) FROM nba.transaction_log', db_con)['max'][0] - timedelta(days=7) # four days leway, unless records are added late

        async def search_transactions(starting_row, transaction_type) -> str:
            return await pst.Search(
                league = pst.League.NBA,
                transaction_types = [transaction_type], # Needs to list, hence []
                start_date = date_from,
                end_date = date.today() + timedelta(2),
                starting_row = starting_row
            ).get_dict()
        
        df = DataFrame()
        pst_page = asyncio.get_event_loop()
        for t_t in pst.TransactionType:
            pages = pst_page.run_until_complete(search_transactions(0, t_t))['pages']
            print(t_t, '-', pages)

            for page in range(pages):
                df_t = pst_page.run_until_complete(search_transactions(page * 25, t_t))
                df_t = DataFrame(df_t['transactions'])
                df_t['transaction_type'] = t_t.name
                df = concat([df, df_t], axis=0, ignore_index=True)
                sleep(1)
        
        df['acc_req'] = ['Acquired' if len(row[1]['Relinquished'])==0 else 'Relinquished' for row in df.iterrows()]
        df['player'] = [row[1]['Acquired'] if len(row[1]['Relinquished'])==0 else row[1]['Relinquished'] for row in df.iterrows()]
        df['player'] = df['player'].str.removeprefix('• ')
        df.columns = df.columns.str.lower()
        df['date'] = to_datetime(df['date']).dt.date
        df = df[col_order]
        
        # Write to database
        df_t = read_sql("SELECT * FROM nba.transaction_log WHERE date >= '{}'".format(date_from), db_con)
        df = concat([df, df_t], axis=0, ignore_index=True)
        df = df[~df.duplicated(keep = False)].reset_index(drop=True)
        df.to_sql('transaction_log', db_con, schema='nba', index=False, if_exists='append')
        print('\ntransaction_log has been updated\n\n')


    
          
    def fty_con(self, db_con):
        """ Create connection object to fanstasy api """

        df_leagues = read_sql(f"SELECT platform, league_id FROM fty.league WHERE season = '{Season.current_season}'", db_con)

        parser = configparser.ConfigParser()
        parser.read(getcwd() + '/database.ini')
        
        fty_con = {}
        for row in df_leagues.iterrows():
            
            fty_creds = dict(parser.items(row[1]['platform'].lower() + '_api'))
            fty_creds['league_id'] = row[1]['league_id']
            
            if row[1]['platform'] == 'ESPN':
                fty_creds['year'] = str(Season.current_season_year+1)
                
                fty_con['ESPN;' + str(row[1]['league_id'])] = bb.League(
                    league_id=int(fty_creds['league_id']),
                    year=int(fty_creds['year']),
                    espn_s2=fty_creds['espn_s2'], 
                    swid=fty_creds['swid']
                )
                
            elif row[1]['platform'] == 'Yahoo':
                fty_creds['token_time'] = float(fty_creds['token_time'])
                
                fty_con['Yahoo;' + str(row[1]['league_id'])] = YahooFantasySportsQuery(
                    league_id=fty_creds['league_id'],
                    game_code="nba",
                    yahoo_access_token_json=fty_creds
                )
                
        return fty_con



    # ADD YAHOO    
    def fty_get_free_agents(self, fty_con, db_con):

        for con in fty_con:
            if con.startswith('ESPN'):
                df = _espn_get_free_agents(fty_con[con])
            elif con.startswith('Yahoo'):
                df = _yahoo_get_free_agents(fty_con[con])

            # Write to database
            # FIX COL ORDER ????
            db_con.connect().execute(text(f"DELETE FROM fty.free_agents WHERE season = '{Season.current_season}' AND platform = '{con.split(';')[0]}' AND league = {con.split(';')[1]}"))
            df.to_sql('free_agents', db_con, schema='fty', index=False, if_exists='append')
            
        print('free_agents has been updated\n\n')

    def _espn_get_free_agents(fty_con):
        
        df = []
        for free_agent in fty_con.free_agents(size=1000):
            df.append({
                'timestamp': datetime.now(timezone('NZ')),
                'player_id': free_agent.playerId,
                'player_name': free_agent.name,
                'player_team': free_agent.proTeam,
                'player_status': free_agent.injuryStatus,
                'player_position': free_agent.position
            }) 

        df = DataFrame(df)
        df['player_team'] = df['player_team'].str.replace('PHL', 'PHI')
        df['player_team'] = df['player_team'].str.replace('PHO', 'PHX')
        df['platform'] = 'ESPN'
        df['season'] = Season.current_seasn
        df['league_id'] = fty_con.league_id

        return df

    # TODO
    def _yahoo_get_free_agents(fty_con):
        
        df = []
        # Injury and Free agent status of players, competitor roster
        fty_con.get_league_players()[0].ownership
        fty_con.get_league_players()[0].status
        fty_con.get_league_players()[0].status_full

        df = DataFrame(df)
        df['player_team'] = df['player_team'].str.replace('PHL', 'PHI')
        df['player_team'] = df['player_team'].str.replace('PHO', 'PHX')
        df['platform'] = 'Yahoo'
        df['season'] = Season.current_seasn
        df['league_id'] = fty_con.league_id

        return df



    # ADD YAHOO  
    def fty_get_league_competitor(self, fty_con, db_con):

       for con in fty_con:
            if con.startswith('ESPN'):
                df = _espn_get_league_competitor(fty_con[con])
            elif con.startswith('Yahoo'):
                df = _yahoo_get_league_competitor(fty_con[con])

            # Write to database
            df.to_sql('league_competitor', db_con, schema='fty', index=False, if_exists='append')
        print('league_competitor has been updated\n\n')

    def _espn_get_league_competitor(fty_con):

        df = []
        for competitor in fty_con.teams:
            df.append({
                'season': Season.current_season,
                'platform': , 'ESPN',
                'league_id': fty_con.league_id,
                # 'league_name': fty_con.settings.name, DELETE
                'competitor_id': competitor.team_id,
                'competitor_abbrev': competitor.team_abbrev,
                'competitor_name': competitor.team_name, 
                'division_id': competitor.division_id, # DELETE
                'division_name': competitor.division_name # DELETE
            })
            
        return DataFrame(df)

    # TWEAK REQ
    def _yahoo_get_league_competitor(fty_con):

        df = []
        for competitor in fty_con.get_league_teams():
        
            df.append({
                'season': Season.current_season,
                'platform': 'Yahoo',
                'league_id': fty_con.league_id,
                # 'league_name': query.get_league_metadata().name.decode(),
                'competitor_id': competitor.team_id,
                'competitor_abbrev': competitor.managers[0].nickname,
                'competitor_name': competitor.name.decode(),
                'division_id': None, # DELETE
                'division_name': None # DELETE
            })
        
        return DataFrame(df)



    # ADD YAHOO  
    def fty_get_league_schedule(self, fty_con, db_con):

        for con in fty_con:
            if con.startswith('ESPN'):
                df = _espn_get_league_schedule(fty_con[con], db_con)
            elif con.startswith('Yahoo'):
                df = _yahoo_get_league_schedule(fty_con[con])

            # Write to database
            df.to_sql('league_schedule', db_con, schema='fty', index=False, if_exists='append')
        print('league_schedule has been updated\n\n')

    def _espn_get_league_schedule(fty_con, db_con):

        league_start_date = read_sql(f"SELECT begin_date FROM util.key_dates WHERE season = '{Season.current_season}' AND season_type = 'Regular Season'", db_con)['begin_date'][0]
        league_start_date = league_start_date + timedelta(days = -league_start_date.weekday())

        df = []
        for competitor in fty_con.teams:
            for ix, opponent in enumerate(competitor.schedule):
                df.append({
                    'season': Season.current_season, 
                    'platform': 'ESPN',
                    'league_id': fty_con.league_id, 
                    'week': ix + 1, 
                    'week_start': (league_start_date + timedelta(weeks=ix)).date(),
                    'week_end': (league_start_date + timedelta(weeks=ix+1) - timedelta(days=1)).date(),
                    'competitor_id': competitor.team_id, 
                    'competitor_name': competitor.team_name, # DELETE
                    'opponent_id': opponent.home_team.team_id if competitor.team_id == opponent.away_team.team_id else opponent.away_team.team_id,
                    'opponent_name': opponent.home_team.team_name if competitor.team_id == opponent.away_team.team_id else opponent.away_team.team_name # DELETE
                })

    def _yahoo_get_league_schedule(fty_con):
        
        df = []
        for team_id in [team.team_id for team in fty_con.get_league_teams()]:
            for match in fty_con.get_team_matchups(team_id):
                df.append({
                    'season': Season.current_season,
                    'platform': 'Yahoo',
                    'league_id': fty_con.league_id,
                    'week': match.week,
                    'week_start': match.week_start,
                    'week_end': match.week_end,
                    'competitor_id': team_id,
                    'competitor_name': None, # DELETE
                    'opponent_id': match.teams[1].team_id
                    'opponent_name': None, # DELETE
                })
                
            return DataFrame(df)



    # ADD YAHOO  
    def fty_get_competitor_roster(self, fty_con, db_con):

        df = []
        for competitor in fty_con.teams:
            for player in competitor.roster:
                df.append({
                    'season': Season.current_season, 
                    'platform': 'ESPN',
                    'league_id': fty_con.league_id, 
                    'timestamp': datetime.now(timezone('NZ')), 
                    'league_week': fty_con.currentMatchupPeriod, # fty_con.league_week does not give the current week...
                    'competitor_id': competitor.team_id, 
                    'competitor_name': competitor.team_name, # DELETE
                    'player_fantasy_id': player.playerId, 
                    'player_name': player.name, 
                    'player_team': player.proTeam,
                    'player_injury_status': player.injuryStatus,
                    'player_acquisition_type': player.acquisitionType
                })

        # ADD PLATFORM HERE
        
        df = DataFrame(df)
        df['player_team'] = df['player_team'].str.replace('PHL', 'PHI')
        df['player_team'] = df['player_team'].str.replace('PHO', 'PHX')

        # Write to database
        df.to_sql('competitor_roster', db_con, schema='fty', index=False, if_exists='append')
        print('competitor_roster has been updated\n\n')



    # ADD YAHOO  
    def fty_get_recent_activity(self, fty_con, db_con):

        df = []
        for activity in fty_con.recent_activity(size=50):
            for action in activity.actions:
                df.append({
                    'timestamp': datetime.fromtimestamp(activity.date / 1000),
                    'competitor_id': action[0].team_id,
                    'competitor_name': action[0].team_name,
                    'action': action[1],
                    'player': action[2] 
                })
        
        df = DataFrame(df)

        # NEED TO ADD SEASON, PLATFORM, LEAGUE_ID

        df_t = read_sql("SELECT * FROM fty.recent_activity", db_con)
        df = concat([df, df_t], ignore_index=True).drop_duplicates()
        df.to_sql('recent_activity', db_con, schema='fty', index=False, if_exists='replace')
        print('recent_activity has been updated\n\n')



    # ADD YAHOO  
    def fty_get_matchup_box_score(self, fty_con, db_con):
        # NEED TO TEST IF THIS WORKS
        # PARTICULARLY ON MONDAY MORNINGS WHERE MATCHUP PERIOD COULD BE WRONG

        df = [] 
        stats = ['PTS', 'BLK', 'STL', 'AST', 'REB', 'TO', 'FGM', 'FGA', 'FTM', 'FTA', '3PTM', 'FG%', 'FT%']

        period = fty_con.currentMatchupPeriod if date.today().strftime('%a') != 'Mon' else fty_con.currentMatchupPeriod - 1
        box_score = fty_con.box_scores(matchup_period = period)
        
        for matchup in box_score:
            for h_a in ['home', 'away']:
                
                competitor = getattr(matchup, h_a + '_team')
                competitor_stats = getattr(matchup, h_a + '_stats')
    
                df.append(
                    DataFrame({
                        ** {
                            'season': fty_con.year,
                            'league_id': fty_con.league_id,
                            'competitor_id': competitor.team_id,
                            'matchup': period
                        } ,
                        ** dict(zip(stats, [competitor_stats[stat]['value'] for stat in stats]))
                    })
                )

        # ADD PLATFORM HERE
                    
        df = concat(df)
        df = df.rename(snakecase.convert, axis='columns')
        df = df.rename({'3ptm': 'fg3_m', 'fg%': 'fg_pct', 'ft%': 'ft_pct', 'to': 'tov'})
    
        # CONCAT WITH QUERY THAT eXCLUDES MATCHUP PERIOD
        df = concat([
            read_sql(
                """
                SELECT * 
                FROM fty.matchup_box_score 
                WHERE NOT (season = {} AND league_id = {} AND matchup = {})
                """.format(fty_con.year, fty_con.league_id, period),
                db_con
            ), 
            df
        ])
        
        # df.write_database('fty.matchup_box_score', db_con.url, if_table_exists='replace')


    
    










        