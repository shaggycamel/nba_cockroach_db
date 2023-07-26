
import pandas as pd
from dataHub import dataHub
dh = dataHub()

# postgre_con = dh.db_connect('postgre')
fty_con = dh.fty_api_con()


player_season_stats = dh.get_player_season_stats('postgre_con')
player_info = dh.get_player_info('postgre_con')
player_game_log = dh.get_player_game_log('postgre_con')
hist_game_schedule = dh.update_historical_game_schedule('postgre_con')
next_game_schedule = dh.get_next_game_schedule('postgre_con')
team_roster = dh.get_team_roster('postgre_con')
free_agents = dh.fty_get_free_agents(fty_con.free_agents(size=1000), 'postgre_con')
