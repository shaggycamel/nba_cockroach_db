
import pandas as pd
from sqlalchemy.dialects.postgresql.base import PGDialect; PGDialect._get_server_version_info = lambda *args: (9, 2)
from dataHub import dataHub
dh = dataHub()

cockroach_con = dh.db_connect('cockroach')
fty_con = dh.fty_api_con()


player_season_stats = dh.get_player_season_stats(cockroach_con)
player_info = dh.get_player_info(cockroach_con)
player_game_log = dh.get_player_game_log(cockroach_con)
hist_game_schedule = dh.update_historical_game_schedule(cockroach_con)
next_game_schedule = dh.get_next_game_schedule(cockroach_con)
team_roster = dh.get_team_roster(cockroach_con)
free_agents = dh.fty_get_free_agents(fty_con.free_agents(size=1000), 'cockroach_con')
