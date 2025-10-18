import configparser
import snakecase
import re
import nest_asyncio; nest_asyncio.apply() # needed for running code in jupyter
import espn_api.basketball as bb
from os import getcwd
from requests import get
from datetime import datetime, date, timedelta
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
from nba_api.stats.endpoints import playercareerstats, commonplayerinfo, playergamelog, leaguegamelog, commonteamroster, boxscoreadvancedv2, boxscoretraditionalv2
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
        df = concat(dfs)
        df = df.rename(snakecase.convert, axis='columns')
        df = df.rename(columns = {'season_id': 'season'})
        df = df[df['season'] == self.cur_season]
        df = df[col_order]

        # Write to database
        df.to_sql('player_season_stats', self.db_con, schema='nba', index=False, if_exists='append')
        print('nba.player_season_stats has been updated\n\n')
        


    
    def get_player_info(self):

        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'player_info' ORDER BY column_order", self.db_con)['column_name'].to_list()
        ls_pl = self.active_players['id'].to_list() #[550:615]

        print('\n--------------------- nba.player_info')
        dfs = []
        for player in ls_pl:
            player_info = commonplayerinfo.CommonPlayerInfo(player_id=str(player))
            player_info = player_info.data_sets[0].get_data_frame()
            dfs.append(player_info)
            ix = ls_pl.index(player)
            if ix % 50 == 0: 
                print('player:', ix, '/', len(ls_pl))
            sleep(1)
        print('player:', ix, '/', len(ls_pl))

        # Clean up for ingestion into database
        df = concat(dfs)
        df['HEIGHT'] = [None if (el is None or el == '') else el for el in df['HEIGHT']]
        df['WEIGHT'] = [None if (el is None or el == '') else el for el in df['WEIGHT']]
        df['HEIGHT_CM'] = [round((float(el[0]) * 12 + float(el[1])) * 2.54, 2) if el is not None else None for el in df['HEIGHT'].str.split('-')]
        df['WEIGHT_KG'] = [round(float(el) / 2.2046, 3) if el is not None else None for el in df['WEIGHT']]
        df['season'] = self.cur_season
        df = df.rename(snakecase.convert, axis='columns').rename(columns = {'person_id': 'player_id'})
        df = df[col_order]

        # Write to database
        df.to_sql('player_info', self.db_con, schema='nba', index=False, if_exists='append')
        print('nba.player_info has been updated\n\n')

    

    # TEST IF THIS WORKS
    def get_team_injuries(self):

        # INNER FUNCTION
        def str_search(df, str_pat, col_ix, col_name):
            if (False in [str_pat in el for el in df.iloc[:, col_ix] if el is not nan]):
                df.insert(loc=col_ix, column=col_name, value=nan)
            else:
                df.columns.values[col_ix] = col_name
            return df
        
        # INNER FUNCTION
        def occ_count_search(df, df_true, col_ix, col_name):
            df_search = DataFrame({col_name: [el for el in df.iloc[:, col_ix] if el is not nan]}).value_counts().reset_index()
            if (merge(df_true, df_search, on=col_name, how='left')['count'].sum() == 0):
               df.insert(loc=col_ix, column=col_name, value=nan)
            else:
                df.columns.values[col_ix] = col_name
            return df 

        url = f"https://official.nba.com/nba-injury-report-{self.cur_season}-season/" # URL from which pdfs to be downloaded
        response = get(url) # Requests URL and get response object
        soup = BeautifulSoup(response.text, 'html.parser') # Parse text obtained
        links = soup.find_all('a') # Find all hyperlinks present on webpage

        # Get times of readings and select the latest
        readings_time = {}; readings_pdf = {}
        for link in links:
            if link.decode_contents().endswith('ET report'):
                readings_time[link.contents[0]] = parse(link.contents[0], fuzzy=True, ignoretz=True)
                readings_pdf[link.contents[0]] = get(link.get('href'))

        # Write pdf file
        pdf = open('injury.pdf', 'wb')
        pdf.write(readings_pdf[max(readings_time, key = readings_time.get)].content)
        pdf.close()

        top = 75; left = 19; width = 804; height = 438 # Where to search on pdf file
        dfs = read_pdf('injury.pdf', area=[top, left, top+height, left+width], pages='all') # pdf pages

        # Data objects used to reconcile and complimet injury date
        status_true = DataFrame({'Current Status': ['Available', 'Probable', 'Questionable', 'Out']})
        teams_true = read_sql("SELECT CONCAT(team_long, ' ', team_name) AS team, team_slug FROM nba.teams", self.db_con).rename({'team': 'Team'}, axis='columns')
        
        cur_date = datetime.now().date() - timedelta(days=1) # TWEAK THIS AND QUERY 
        game_ids = read_sql(f"SELECT game_date, game_id, matchup FROM nba.league_game_schedule WHERE game_date BETWEEN '{cur_date}' AND '{cur_date + timedelta(days=2)}'", self.db_con)
        game_ids['game_date'] = to_datetime(game_ids['game_date'])
        game_ids = concat([
            game_ids.assign(matchup = lambda x: x.matchup.str.replace(' vs. ', '@')),
            game_ids.assign(matchup = lambda x: [el[1] + '@' + el[0] for el in x.matchup.str.split(' vs. ')])    
        ], ignore_index=True, axis='rows')
        
        player_ids = read_sql("SELECT nba_name, nba_id FROM util.nba_fty_name_match", self.db_con)
        player_ids['nba_name'] = [normalize('NFKD', el).encode('ascii', 'ignore').decode('utf-8') for el in player_ids['nba_name']] 
        
        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'injuries' ORDER BY column_order", self.db_con)['column_name'].to_list()
    
        # Loop over pdf files, where the magic happens    
        for ix, df in enumerate(dfs):
        
            if ix > 0:
        
                # Move column names to row, excluding first df
                colnames_temp = ['Unnamed: ' + str(el) for el in list(range(0, len(df.columns)))]
                df = (concat([
                    DataFrame({key : nan if 'Unnamed' in val else val for key, val in dict(zip(colnames_temp, df.columns)).items()}, index=[0]),
                    df.set_axis(colnames_temp, axis=1)
                ]))
        
                # Column checks
                df = str_search(df, '/', 0, 'Game Date') # first col date search
                df = str_search(df, ':', 1, 'Game Time') # second col time search
                df = str_search(df, '@', 2, 'Matchup') # third col matchup search
                df = occ_count_search(df, teams_true, 3, 'Team') # fourth col test for team
                df = str_search(df, ',', 4, 'Player Name') # fifth col test for player name
                df = occ_count_search(df, status_true, 5, 'Current Status') # sixth col test for status
                df.columns.values[6] = 'Reason' # straigt rename of seventh column
                
            # assign back to index in list
            dfs[ix] = df
        
        # Merge all and clean
        df = concat(dfs).reset_index(drop=True)
        df['Game Date'] = df['Game Date'].ffill().bfill()
        df['Game Time'] = df['Game Time'].ffill().bfill()
        df['Matchup'] = df['Matchup'].ffill().bfill()
        df['Team'] = df['Team'].ffill().bfill()
        df['Reason_lead'] = df.groupby('Team')['Reason'].shift(-1)
        
        # Fix poorly formatted injury rows
        inj_ix = df[(df['Reason_lead'].isna()) & (df['Reason'].str.startswith('Injury/Illness')) & (df['Team'] == df['Team'].shift(-1))].index
        for ix in inj_ix:
        
            # Rows of interest
            df_temp = df.iloc[range(ix, ix+3), :]
        
            # Overwrite rows
            df.loc[range(ix, ix+3), 'Player Name'] = [' '.join(df_temp['Player Name'].dropna())]*3
            df.loc[range(ix, ix+3), 'Current Status'] = [' '.join(df_temp['Current Status'].dropna())]*3
            df.loc[range(ix, ix+3), 'Reason'] = [' '.join(df_temp['Reason'].dropna())]*3
        
        # Drop duplicates and non-submissions & non-names (cheat...for now until better solution)
        df = (
            df.drop('Reason_lead', axis='columns')
            .drop_duplicates()
            .query('Reason != "NOT YET SUBMITTED"')
            .query('`Player Name`.notna()')
            .query('`Game Date`.notna()')
        )
        
        # Convert columns
        df['Game Date'] = to_datetime(df['Game Date'], format='%m/%d/%Y')
        df['Player Name'] = [el[1] + ' ' + el[0] for el in df['Player Name'].str.split(', ')]
        
        # Join external dataset
        df = df.merge(teams_true, how = 'left', on='Team') # team slug
        df = df.merge(game_ids, how = 'left', left_on=['Game Date', 'Matchup'], right_on=['game_date', 'matchup']).drop(['game_date', 'matchup'], axis=1)
        df = df.merge(player_ids, how = 'left', left_on='Player Name', right_on='nba_name')
        
        # Rename cols and reorder
        df.columns = df.columns.str.lower().str.replace(' ', '_')
        df = df.rename(columns = {'current_status': 'status'})
        df = df[col_order]
        
        # Delete old records from database
        db_ex = self.db_con.connect()
        for _, row in df.iterrows():
            game_date = row['game_date']
            game_id = row['game_id']
            player_name = row['player_name'].replace("'","''") # replace to handle single quotes if they exist
            db_ex.execute(text(f"DELETE FROM nba.injuries WHERE game_date = '{game_date}' AND game_id = {game_id} AND player_name = '{player_name}'"))
        db_ex.commit()
        
        # Write to database
        df.to_sql('injuries', self.db_con, schema='nba', index=False, if_exists='append')
        print('nba.injuries has been updated\n\n')


    
    # NEED TO CHECK IF WORKS
    def get_box_score(self):

        bs_max_dt = (
            read_sql("""
                SELECT MAX(ls.game_date) 
                FROM nba.team_box_score AS bs
                INNER JOIN nba.league_game_schedule AS ls on bs.game_id = ls.game_id
            """, self.db_con)
            ['max'][0]
            .strftime('%Y-%m-%d')
        )
        
        game_ids = (
            read_sql(f"""
                SELECT game_id, game_date
                FROM nba.league_game_schedule
                WHERE game_date > '{bs_max_dt}' AND game_date <= current_date
            """, self.db_con)
        )
        
        trad_adv_lst = ['player', 'team']

        print('\n--------------------- nba.player/team_box_score')
        g_ids = game_ids['game_id'] # [0:55]
        for game_id in g_ids:
            game_id = '00' + str(int(game_id))
            print(game_id)
        
            dfs = []
            bsa = boxscoreadvancedv2.BoxScoreAdvancedV2(game_id=game_id)
            if len(bsa.get_normalized_dict()['PlayerStats']) == 0:
                continue
        
            bst = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
            
            for el in [0, 1]:
        
                bst_col_order = read_sql(f"SELECT column_name FROM util.table_column_order WHERE table_name = '{trad_adv_lst[el]}_box_score_traditional' ORDER BY column_order", self.db_con)['column_name'].to_list()
                bsa_col_order = read_sql(f"SELECT column_name FROM util.table_column_order WHERE table_name = '{trad_adv_lst[el]}_box_score_advanced' ORDER BY column_order", self.db_con)['column_name'].to_list()
                
                bst_df = (
                    bst
                    .get_data_frames()[el]
                    .rename(snakecase.convert, axis='columns')
                    .rename(columns={'to': 'tov'}) # conform with col_order
                    .drop_duplicates()
                    .assign(game_id = lambda x: x['game_id'].astype('int'))
                    .assign(min = lambda x: [int(re.sub(r':.*', '', el)) if el is not None else None for el in x['min']])
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
                df = df.rename(columns = {'to': 'tov'})
                dfs.append(df)
        
            dfs[0].to_sql('player_box_score', self.db_con, schema='nba', index=False, if_exists='append')
            dfs[1].to_sql('team_box_score', self.db_con, schema='nba', index=False, if_exists='append')

        print('nba.player/team_box_score have been updated\n\n')

        

    
    def update_past_game_schedule(self, season='current'):
        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order", self.db_con)['column_name'].to_list()
        
        if season == 'current':
            season = self.cur_season_year
        else:
            season = self.prev_season_year

        print('\n--------------------- nba.historical_league_game_schedule')
        df = DataFrame() 
        for type_season in ['Regular Season', 'Pre Season', 'Playoffs', 'All Star']:
            hist_game_schedule = leaguegamelog.LeagueGameLog(season_type_all_star=type_season, season=(season-1))
            hist_game_schedule = hist_game_schedule.get_data_frames()[0]
            hist_game_schedule['type_season'] = type_season
            df = concat([df, hist_game_schedule], ignore_index=True)
            sleep(1)

        df['GAME_ID'] = df['GAME_ID'].astype(float)
        df = df.groupby(['GAME_ID']).head(1)
        df['GAME_DATE'] = [parse(el).date() for el in df['GAME_DATE']]
        df['opponent'] = df['MATCHUP'].str.replace(r'[ @ | vs. ]', '', regex=True)
        df['opponent'] = df.apply(lambda x: x['opponent'].replace(x['TEAM_ABBREVIATION'], ''), axis=1)
        df['team_winner'] = where(df['WL'] == 'W', df['TEAM_ABBREVIATION'], df['opponent'])
        df['team_loser'] = where(df['WL'] == 'L', df['TEAM_ABBREVIATION'], df['opponent'])
        df['season'] = f"{season}-{str(season+1)[-2:]}"
        df = df.rename(snakecase.convert, axis='columns')
        df = df.rename(columns = {'type_season': 'season_type'})
        df = df[col_order]

        db_ex = self.db_con.connect()
        db_ex.execute(text(f"DELETE FROM nba.league_game_schedule WHERE season = '{season}-{str(season+1)[-2:]}'"))
        db_ex.commit()

        df.to_sql('league_game_schedule', self.db_con, schema='nba', index=False, if_exists='append')
        print('nba.historical_game_schedule has been updated\n\n')


    
    
    def get_next_game_schedule(self, update_db=True):
        key_dates = read_sql('SELECT * FROM nba.key_dates', self.db_con)
        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order", self.db_con)['column_name'].to_list()
        request = get('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json')

        df = []
        for game_date in request.json()['leagueSchedule']['gameDates']:
            for game in game_date['games']:
                df.append({
                    'game_id': int(game['gameId']),
                    'game_date': parse(game_date['gameDate']).date(),
                    'matchup': game['homeTeam']['teamTricode'] + ' vs. ' + game['awayTeam']['teamTricode']
                })

        df = DataFrame(df)
        df['season'] = self.cur_season
        df['team_winner'] = None
        df['team_loser'] = None
        df = (
            sqldf("""
                SELECT key_dates.season_type, df.*
                FROM df
                LEFT JOIN key_dates ON df.game_date >= key_dates.begin_date 
                    AND df.game_date <= key_dates.end_date
            """, locals())
            [col_order]
            .drop_duplicates()
        )

        # ACTIVATE THIS LATER WHEN IN-Season tourney games and All star games are added to schedule
        # code to take head
        # groupby gameid, sort season type - regualr on bottom
        # slice max
        # df = (
        #     df
        #     .sort_values(['season_type'])
        #     .groupby('game_id')
        #     .head(1)
        # )

        db_ex = self.db_con.connect()
        db_ex.execute(text(f"DELETE FROM nba.league_game_schedule WHERE season = '{self.cur_season}'"))
        db_ex.commit()

        # Write to database
        if update_db:
            df.to_sql('league_game_schedule', self.db_con, schema='nba', index=False, if_exists='append')
            print('nba.current_game_schedule has been updated\n\n')
        else:
            return df



    
    def get_team_roster(self):
        col_order = read_sql("SELECT column_name FROM util.table_column_order WHERE table_name = 'team_roster' ORDER BY column_order", self.db_con)['column_name'].to_list()
        
        print('\n--------------------- nba.team_roster')
        df = DataFrame()
        for team in self.nba_teams['id'].to_list():
            common_teamroster = commonteamroster.CommonTeamRoster(season=self.cur_season_year, team_id=team)
            common_teamroster = common_teamroster.get_data_frames()[0]
            df = concat([df, common_teamroster], ignore_index=True)
            ix = self.nba_teams['id'].to_list().index(team)
            if ix % 5 == 0: 
                print('team:', ix, '/', len(self.nba_teams['id'].to_list()))
            sleep(1)
        print('team:', ix, '/', len(self.nba_teams['id'].to_list()))
        
        df = df.merge(
            self.nba_teams[['id', 'abbreviation']].rename(columns={'id': 'TeamID', 'abbreviation': 'team_slug'}), 
            on=['TeamID'],
            how = 'left'
        )
        df['NUM'] = [None if (el is None or el == '') else el for el in df['NUM']]
        df = df.rename(snakecase.convert, axis='columns')
        df['season'] = self.cur_season
        df['salary'] = None; df['salary'] = df['salary'].astype(float)
        df['movement_date'] = None; df['movement_date'] = to_datetime(df['movement_date'])
        df = df[col_order]

        # CONTROL FOR PLAYERS BEING TRADED
        # df_t = read_sql(f"SELECT * FROM nba.team_roster WHERE season = '{self.cur_season}'", db_con)
        # df_t = df_t.drop('salary', axis='columns')
        # df = concat([df, df_t])
        # df = df[~df.duplicated(keep = False)].reset_index(drop=True)
        
        # Write to database
        df.to_sql('team_roster', self.db_con, schema='nba', index=False, if_exists='append')
        print('nba.team_roster has been updated\n\n')

    
          
    def _fty_con(self):
        """ Create connection object to fanstasy api """

        df_leagues = read_sql(f"SELECT platform, league_id FROM fty.league WHERE season = '{self.cur_season}'", self.db_con)

        parser = configparser.ConfigParser()
        parser.read(getcwd() + '/database.ini')
        
        fty_con = {}
        for row in df_leagues.iterrows():
            
            fty_creds = dict(parser.items(row[1]['platform'].lower() + '_api'))
            fty_creds['league_id'] = row[1]['league_id']
            
            if row[1]['platform'] == 'ESPN':
                fty_creds['year'] = str(self.cur_season_year+1)
                
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
                    game_code='nba',
                    yahoo_access_token_json=fty_creds
                )

                # Set game_id attribute
                fty_con['Yahoo;' + str(row[1]['league_id'])].game_id = \
                    int(fty_con['Yahoo;' + str(row[1]['league_id'])].get_league_key(self.cur_season_year)[0:3])
                
        return fty_con



    def fty_get_free_agents(self):

        # Delete from database
        db_ex = self.db_con.connect()
        db_ex.execute(text("TRUNCATE TABLE fty.free_agents"))
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.free_agents')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_free_agents(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_free_agents(self.fty_con[con]))

        # Write to database
        concat(dfs, ignore_index=True).to_sql('free_agents', self.db_con, schema='fty', index=False, if_exists='append')
        print('fty.free_agents has been updated\n\n')

    def _espn_get_free_agents(self, espn_con):
        
        df = []
        for free_agent in espn_con.free_agents(size=1000):
            df.append({
                'season': self.cur_season,
                'platform': 'ESPN',
                'league_id': espn_con.league_id,
                'timestamp': datetime.now(timezone('NZ')),
                'player_id': free_agent.playerId,
                'player_name': free_agent.name,
                'player_team': free_agent.proTeam.replace('PHL', 'PHI').replace('PHO', 'PHX'),
                'player_injury_status': free_agent.injuryStatus,
                'player_position': free_agent.position
            })

        return DataFrame(df)

    def _yahoo_get_free_agents(self, yahoo_con):
        
        df = []
        for player in yahoo_con.get_league_players():
            p_ownership = yahoo_con.get_player_ownership(player.player_key)
            if p_ownership.ownership.ownership_type in ['freeagents', 'waivers']:
                df.append({
                    'season': self.cur_season,
                    'platform': 'Yahoo',
                    'league_id': yahoo_con.league_id, 
                    # 'timestamp': datetime.now(timezone('NZ')), # insert afterwards
                    'player_id': p_ownership.player_id,
                    'player_name': p_ownership.name.full,
                    'player_team': p_ownership.editorial_team_abbr,
                    'player_injury_status': player.status,
                    'player_position': p_ownership.display_position
                })
                sleep(1)

        df = DataFrame(df)
        df['player_injury_status'] = ['ACTIVE' if el == '' else el for el in df['player_injury_status']]
        df.insert(3, 'timestamp', datetime.now(timezone('NZ')))
        return df


    def fty_get_league_competitor(self):

        # Remove existing records from database (if any)
        db_ex = self.db_con.connect()
        db_ex.execute(text(f"DELETE FROM fty.league_competitor WHERE season = '{self.cur_season}'"))
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.league_competitor')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_league_competitor(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_league_competitor(self.fty_con[con]))

        # Write to database
        concat(dfs, ignore_index=True).to_sql('league_competitor', self.db_con, schema='fty', index=False, if_exists='append')
        print('\nfty.league_competitor has been updated\n\n')
        

    def _espn_get_league_competitor(self, espn_con):

        df = []
        for competitor in espn_con.teams:
            df.append({
                'season': self.cur_season,
                'platform': 'ESPN',
                'league_id': espn_con.league_id,
                'competitor_id': competitor.team_id,
                'competitor_abbrev': competitor.team_abbrev,
                'competitor_name': competitor.team_name
            })
            
        return DataFrame(df)

    def _yahoo_get_league_competitor(self, yahoo_con):

        df = []
        for competitor in yahoo_con.get_league_teams():
        
            df.append({
                'season': self.cur_season,
                'platform': 'Yahoo',
                'league_id': yahoo_con.league_id,
                'competitor_id': competitor.team_id,
                'competitor_abbrev': competitor.managers[0].nickname,
                'competitor_name': competitor.name.decode()
            })
        
        return DataFrame(df)

    # NEW: TEST
    def fty_get_league_matchup(self):

        # Remove existing records from database (if any)
        db_ex = self.db_con.connect()
        db_ex.execute(text(f"DELETE FROM fty.league_matchup WHERE season = '{self.cur_season}'"))
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.league_matchup')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_league_matchup(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_league_matchup(self.fty_con[con]))

        # Write to database
        concat(dfs, ignore_index=True).to_sql('league_matchup', self.db_con, schema='fty', index=False, if_exists='append')
        print('fty.league_matchup has been updated\n\n')

    def _espn_get_league_matchup(self, espn_con):

        lg_mup = []
        for competitor in espn_con.teams:
            for ix, opponent in enumerate(competitor.schedule):
                lg_mup.append({
                    'season': self.cur_season,
                    'platform': 'ESPN',
                    'league_id': espn_con.leage_id,
                    'matchup_period': ix + 1, 
                    'competitor_id': competitor.team_id, 
                    'opponent_id': opponent.home_team.team_id if competitor.team_id == opponent.away_team.team_id else opponent.away_team.team_id
                })

        return DataFrame(lg_mup).sort_values(['matchup_period', 'competitor_id'])

    def _yahoo_get_league_matchup(self, yahoo_con):
        # YET TO IMPLEMENT
        pass

    # NEW: TEST
    def fty_get_league_matchup_dates(self):

        # Remove existing records from database (if any)
        db_ex = self.db_con.connect()
        db_ex.execute(text(f"DELETE FROM fty.league_matchup_dates WHERE season = '{self.cur_season}'"))
        db_ex.commit()

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.league_matchup_dates')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_league_matchup_dates(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_league_matchup_dates(self.fty_con[con]))

        # Write to database
        concat(dfs, ignore_index=True).to_sql('league_matchup_dates', self.db_con, schema='fty', index=False, if_exists='append')
        print(con + ' fty.league_matchup_dates has been updated\n\n')

    def _espn_get_league_matchup_dates(self, espn_con):

        nba_match_dates = []
        p_sch = espn_con.pro_schedule
        for team in p_sch:
            for match_day in p_sch[team]:
                nba_match_dates.append({
                    'match_day': int(match_day), 
                    'date': datetime.fromtimestamp(p_sch[team][match_day][0]['date'] / 1000).date() - timedelta(days=1) # minus one day to get the conversion right
                })

        nba_match_dates = (
            DataFrame(nba_match_dates)
            .drop_duplicates()
            .sort_values('match_day')
        )

        espn_matchup_dates = espn_con.matchup_ids
        espn_matchup_dates = DataFrame([(int(mp), int(md)) for mp, days in espn_matchup_dates.items() for md in days], columns=['matchup_period', 'match_day'])
        espn_matchup_dates = espn_matchup_dates[espn_matchup_dates['match_day'].isin(espn_matchup_dates.groupby('matchup_period')['match_day'].agg(['min','max']).stack())]
        espn_matchup_dates = espn_matchup_dates.sort_values(['matchup_period', 'match_day'])
        espn_matchup_dates = espn_matchup_dates.merge(nba_match_dates, on = 'match_day', how = 'left')

        grp_min = espn_matchup_dates.groupby('matchup_period')['match_day'].transform('min')
        grp_max = espn_matchup_dates.groupby('matchup_period')['match_day'].transform('max')

        espn_matchup_dates['from_to'] = None
        espn_matchup_dates.loc[espn_matchup_dates['match_day'] == grp_min, 'from_to'] = 'matchup_start'
        espn_matchup_dates.loc[espn_matchup_dates['match_day'] == grp_max, 'from_to'] = 'matchup_end'

        return (
            espn_matchup_dates
            .pivot(index='matchup_period', columns='from_to', values='date')
            .rename_axis(columns=None)
            .reset_index()
            .assign(season = self.cur_season, platform = 'ESPN', league_id = espn_con.league_id)
        )

    def _yahoo_get_league_matchup_dates(self, yahoo_con):
        # YET TO IMPLEMENT
        pass


    # EVENTUALLY DELETE AND CHILD FUNCTIONS
    def fty_get_league_schedule(self):

        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.league_schedule')
            if con.startswith('ESPN'):
                df = self._espn_get_league_schedule(self.fty_con[con])
            elif con.startswith('Yahoo'):
                df = self._yahoo_get_league_schedule(self.fty_con[con])

            # Write to database
            df.to_sql('league_schedule', self.db_con, schema='fty', index=False, if_exists='append')
            print(con + ' fty.league_schedule has been updated\n\n')

    def _espn_get_league_schedule(self, espn_con):

        league_start_date = read_sql(f"SELECT begin_date FROM nba.key_dates WHERE season = '{self.cur_season}' AND season_type = 'Regular Season'", self.db_con)['begin_date'][0]
        league_start_date = league_start_date + timedelta(days = -league_start_date.weekday())

        df = []
        for competitor in espn_con.teams:
            for ix, opponent in enumerate(competitor.schedule):
                df.append({
                    'season': self.cur_season, 
                    'platform': 'ESPN',
                    'league_id': espn_con.league_id, 
                    'week': ix + 1, 
                    'week_start': (league_start_date + timedelta(weeks=ix)),
                    'week_end': (league_start_date + timedelta(weeks=ix+1) - timedelta(days=1)),
                    'competitor_id': competitor.team_id, 
                    'opponent_id': opponent.home_team.team_id if competitor.team_id == opponent.away_team.team_id else opponent.away_team.team_id
                })
                
        return DataFrame(df)

    def _yahoo_get_league_schedule(self, yahoo_con):
        
        df = []
        for team_id in [team.team_id for team in yahoo_con.get_league_teams()]:
            for match in yahoo_con.get_team_matchups(team_id):
                df.append({
                    'season': self.cur_season,
                    'platform': 'Yahoo',
                    'league_id': yahoo_con.league_id,
                    'week': match.week,
                    'week_start': match.week_start,
                    'week_end': match.week_end,
                    'competitor_id': team_id,
                    'opponent_id': match.teams[1].team_id
                })
                
        return DataFrame(df)


    

    def fty_get_competitor_roster(self):

        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.competitor_roster')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_competitor_roster(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_competitor_roster(self.fty_con[con]))

        # Write to database
        concat(dfs, ignore_index=True).to_sql('competitor_roster', self.db_con, schema='fty', index=False, if_exists='append')
        print('fty.competitor_roster has been updated\n\n')

    def _espn_get_competitor_roster(self, espn_con):

        df = []
        for competitor in espn_con.teams:
            for player in competitor.roster:
                df.append({
                    'season': self.cur_season, 
                    'platform': 'ESPN',
                    'league_id': espn_con.league_id, 
                    'timestamp': datetime.now(timezone('NZ')), 
                    'matchup_period': espn_con.currentMatchupPeriod,
                    'competitor_id': competitor.team_id, 
                    'player_fantasy_id': player.playerId, 
                    'player_name': player.name, 
                    'player_team': player.proTeam.replace('PHL', 'PHI').replace('PHO', 'PHX'),
                    'player_injury_status': player.injuryStatus,
                    'player_acquisition_type': player.acquisitionType
                })

        return DataFrame(df)

    def _yahoo_get_competitor_roster(self, yahoo_con):

        df = []
        for team_id in [team.team_id for team in yahoo_con.get_league_teams()]:
            for player in yahoo_con.get_team_roster_by_week(team_id).clean_data_dict()['players']:
                if player['player'].selected_position.position != None:
                    df.append({
                        'season': self.cur_season,
                        'platform': 'Yahoo',
                        'league_id': yahoo_con.league_id,
                        'matchup_period': yahoo_con.get_league_info().current_week,
                        'competitor_id': team_id,
                        'player_fantasy_id': player['player'].player_id,
                        'player_name': player['player'].name.full,
                        'player_team': player['player'].editorial_team_abbr,
                        'player_injury_status': player['player'].status,
                        'player_acquisition_type': None
                    })

        df = DataFrame(df)
        df['player_injury_status'] = ['ACTIVE' if el == '' else el for el in df['player_injury_status']]
        df.insert(3, 'timestamp', datetime.now(timezone('NZ')))
        return df

    


    def fty_get_recent_activity(self):
        
        dfs = []
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.recent_activity')
            if con.startswith('ESPN'):
                dfs.append(self._espn_get_recent_activity(self.fty_con[con]))
            elif con.startswith('Yahoo'):
                dfs.append(self._yahoo_get_recent_activity(self.fty_con[con]))

        # Write to database
        concat(dfs, ignore_index=True).to_sql('recent_activity', self.db_con, schema='fty', index=False, if_exists='append')
        print('fty.recent_activity has been updated\n\n')

    def _espn_get_recent_activity(self, espn_con):

        df = []
        for activity in espn_con.recent_activity(size=50):
            for action in activity.actions:
                df.append({
                    'season': self.cur_season,
                    'platform': 'ESPN',
                    'league_id': espn_con.league_id,
                    'timestamp': datetime.fromtimestamp(activity.date / 1000),
                    'competitor_id': action[0].team_id,
                    'action': action[1],
                    'player': action[2] 
                })
        
        df_t = read_sql(f"SELECT * FROM fty.recent_activity WHERE season = '{self.cur_season}' AND platform = 'ESPN' AND league_id = {espn_con.league_id}", self.db_con)
        df = DataFrame(df).merge(df_t, how='outer', indicator=True)
        return df[(df._merge=='left_only')].drop('_merge', axis=1)

    def _yahoo_get_recent_activity(self, yahoo_con):

        df = []
        for activity in yahoo_con.get_league_transactions():
            if activity.type != 'commish':
                for player in activity.players:
                    el_id = [el for el in player.clean_data_dict()['transaction_data'].keys() if el.endswith('_team_key')][0]
          
                    df.append({
                        'season': self.cur_season,
                        'platform': 'Yahoo',
                        'league_id': yahoo_con.league_id,
                        'timestamp': datetime.fromtimestamp(activity.timestamp), 
                        'competitor_id': int(player.clean_data_dict()['transaction_data'][el_id].replace('454.l.121793.t.', '')),
                        'action': player.clean_data_dict()['transaction_data']['type'],
                        'player': player.clean_data_dict()['name']['full']
                    })

        
        df_t = read_sql(f"SELECT * FROM fty.recent_activity WHERE season = '{self.cur_season}' AND platform = 'Yahoo' AND league_id = {yahoo_con.league_id}", self.db_con)
        df = DataFrame(df).merge(df_t, how='outer', indicator=True)
        return df[(df._merge=='left_only')].drop('_merge', axis=1)


 
    def fty_get_matchup_box_score(self):

        # Keep ingestion as league specific because they can have different matchup periods
        for con in self.fty_con:
            print('\n--------------------- ' + con + ' fty.matchup_box_score')
            if con.startswith('ESPN'):
                df = self._espn_get_matchup_box_score(self.fty_con[con], self.db_con)
            elif con.startswith('Yahoo'):
                df = self._yahoo_get_matchup_box_score(self.fty_con[con], self.db_con)

            # Delete from database
            db_ex = self.db_con.connect()
            db_ex.execute(text(f"DELETE FROM fty.matchup_box_score WHERE season = '{self.cur_season}' AND platform = '{con.split(';')[0]}' AND league_id = {con.split(';')[1]} AND matchup = {df['matchup'][0]}"))
            db_ex.commit()
            
            # Write to database
            df.to_sql('matchup_box_score', self.db_con, schema='fty', index=False, if_exists='append')
            print(con + ' fty.matchup_box_score has been updated\n\n')


    def _espn_get_matchup_box_score(self, espn_con):
        
        box_scores = espn_con.box_scores(matchup_period = espn_con.currentMatchupPeriod)
        league_cats = read_sql(f"SELECT * FROM fty.league_categories WHERE platform = 'ESPN' AND season = '{self.cur_season}' AND league_id = {espn_con.league_id}", self.db_con)
        stats = league_cats['fty_categories']

        df = [] 
        for matchup in box_scores:
            for h_a in ['home', 'away']:
                competitor = getattr(matchup, h_a + '_team')
                competitor_stats = getattr(matchup, h_a + '_stats')
        
                if competitor != 0:
                    df.append({
                        ** {
                            'season': self.cur_season,
                            'platform': 'ESPN',
                            'league_id': espn_con.league_id,
                            'competitor_id': competitor.team_id,
                            'matchup': espn_con.currentMatchupPeriod
                        } ,
                        ** dict(zip(stats, [competitor_stats[stat]['value'] for stat in stats]))
                    })

        cat_labels = (
            league_cats
            .merge(
                read_sql("SELECT * FROM fty.category_label WHERE platform = 'ESPN'", self.db_con), 
                how='left', 
                left_on=['platform', 'category'], 
                right_on=['platform', 'fty_category']
            )
            .set_index('fty_category')['db_category']
            .to_dict()
        )
        
        return DataFrame(df).rename(cat_labels, axis='columns')


    def _yahoo_get_matchup_box_score(self, yahoo_con):
        # TRED WITH CAUTION: still need to configure for non-conventional categories

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
        
        box_scores = read_sql(qry, self.db_con)
        box_scores['game_date'] = to_datetime(box_scores['game_date'])

        
        df = []
        for competitor in yahoo_con.get_league_teams():
            for dt in date_range(box_scores['game_date'].min(), box_scores['game_date'].max()):
                for player in yahoo_con.get_team_roster_player_info_by_date(competitor.team_id, dt):
                    if player.selected_position.position not in ['IL+', 'BN']:
                        df.append({'competitor_id': competitor.team_id, 'game_date': dt, 'yahoo_id': player.player_id})    
        
        return (
            DataFrame(df)
            .merge(box_scores, on=['yahoo_id', 'game_date'], how='inner')
            .drop(['yahoo_id', 'game_date', 'game_id'], axis='columns')
            .groupby(by=['season', 'platform', 'league_id', 'competitor_id', 'matchup'], as_index=False)
            .sum()
            .assign(
                fg_pct = lambda x: x['fgm'] / x['fga'],
                ft_pct = lambda x: x['ftm'] / x['fta']
            )
        )

    
    








        