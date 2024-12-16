# To run this file, execute "import refresh_season_schedule" from python console

import pandas as pd; pd.set_option('display.max_columns', 500)
from sqlalchemy.dialects.postgresql.base import PGDialect; PGDialect._get_server_version_info = lambda *args: (9, 2)
from nba_api.stats.library.parameters import Season
from sqlalchemy.sql import text
from dataHub import dataHub

dh = dataHub()
db_con = dh.db_connect('cockroach')

df = dh.get_next_game_schedule(db_con, update_db=False)

# Delete from database
db_ex = db_con.connect()
db_ex.execute(text(f"DELETE FROM nba.league_game_schedule WHERE season = '{Season.current_season}'"))
db_ex.commit()

# Write to database
df.to_sql('league_game_schedule', db_con, schema='nba', index=False, if_exists='append')
print('Updated...')