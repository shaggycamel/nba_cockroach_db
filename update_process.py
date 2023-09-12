from pandas import DataFrame, read_sql_query
from datetime import datetime
from pytz import timezone
from sqlalchemy.dialects.postgresql.base import PGDialect; PGDialect._get_server_version_info = lambda *args: (9, 2)
from dataHub import dataHub

dh = dataHub()
db_connection = dh.db_connect('postgre')
# db_connection = dh.db_connect('cockroach')
fty_con = dh.fty_api_con()


def custom_prelog(func, table_name):
    table_name = table_name
    timestamp = datetime.now(timezone('NZ'))
    try:
        func()
        success = True  
        error_message = None
    except Exception as e:
        success = False
        error_message = str(e)
    finally:
        log_record = DataFrame(
            data={'table_name': table_name, 'process_date': timestamp, 'successful_run': success, 'error_message': error_message}, 
            index=[0]
        )
        log_record.to_sql('update_log', db_connection, schema='util', index=False, if_exists='append')
        
        

custom_prelog(lambda: dh.get_player_season_stats(db_connection), 'nba.player_season_stats')
custom_prelog(lambda: dh.get_player_info(db_connection), 'nba.player_info')
custom_prelog(lambda: dh.get_player_game_log(db_connection), 'nba.player_game_log')
custom_prelog(lambda: dh.update_past_game_schedule(db_connection), 'nba.league_game_schedule/past')
custom_prelog(lambda: dh.get_next_game_schedule(db_connection), 'nba.league_game_schedule/future')
custom_prelog(lambda: dh.get_team_roster(db_connection), 'nba.team_roster')
custom_prelog(lambda: dh.get_transactions(db_connection), 'nba.transaction_log')
custom_prelog(lambda: dh.fty_get_free_agents(fty_con.free_agents(size=1000), db_connection), 'fty.free_agents')


current_date = datetime.now(timezone('NZ')).strftime('%Y-%m-%d')
failed_objects = read_sql_query("SELECT table_name FROM util.update_log WHERE successful_run = False AND process_date::DATE = '{}'".format(current_date), db_connection)

if len(failed_objects) > 0:
    raise Exception(print(current_date, '\nFailed objects:', failed_objects['table_name'].to_list()))
else:
    print(current_date, '\nAll tables successfully updated.')
