from polars_conversion import dataHub
import polars as pl
import polars.selectors as cs
import janitor.polars
import datetime as dt
import zoneinfo
import time
import sqlalchemy
import requests
import dateutil
import nba_api.stats.endpoints as nba_ep

dh = dataHub('postgre')


# def fty_get_competitor_roster(self):

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
    "SELECT * FROM util.table_column_order WHERE table_name = 'competitor_roster'", self.db_con
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
