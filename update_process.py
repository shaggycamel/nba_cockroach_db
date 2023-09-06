
import pandas as pd
from sqlalchemy.dialects.postgresql.base import PGDialect; PGDialect._get_server_version_info = lambda *args: (9, 2)
from dataHub import dataHub
dh = dataHub()

db_connection = dh.db_connect('cockroach')
# fty_con = dh.fty_api_con()

dh.get_player_season_stats(db_connection)
dh.get_player_info(db_connection)
dh.get_player_game_log(db_connection) # dependant on util.key_dates
dh.update_past_game_schedule(db_connection)
dh.get_next_game_schedule(db_connection)
dh.get_team_roster(db_connection)
dh.get_transactions(db_connection)
# dh.fty_get_free_agents(fty_con.free_agents(size=1000), db_connection)
