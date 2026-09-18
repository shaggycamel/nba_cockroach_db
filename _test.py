
from sports_hub import SportsHub
import polars as pl

hub = SportsHub(db_con = 'postgres')

leagues = (
    hub.db.read(f"select * from fty.customer_league where season = '{hub.ctx.cur_season}'")
    .group_by('league_id')
    .first(ignore_nulls=True)
    # .filter(~pl.col('league_id').is_in([95537, 1440301458, 1966813226])) # Remove
)

hub.fty.connect_leagues(leagues=leagues)

# Done manually:
# League matchup dates
# League byes


hub.fty.get_league()
hub.fty.get_league_categories()
hub.fty.get_league_competitor()
hub.fty.get_league_matchup()


