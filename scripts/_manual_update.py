from sports_hub import SportsHub
import polars as pl
import datetime as dt

# hub = SportsHub(db_con = 'postgres')
hub = SportsHub(db_con = 'cockroach')

qry = f"""
    select lg.*, pf.credentials 
    from fty.customer_league as lg
    left join fty.customer_platform as pf on lg.customer_id = pf.customer_id
        and lg.platform = pf.platform
    where season = '{hub.ctx.cur_season}'
"""

leagues = (
    hub.db.read(qry)
    .group_by('league_id')
    .first(ignore_nulls=True)
)

hub.fty.connect_leagues(leagues=leagues)


# ---------------------------------- NBA Data
# STILL NEED TO DO THIS FOR 2026-27

# ---- Player Season Stats
# hub.nba.get_player_box_score()


# ----- Player info
# hub.nba.get_player_info()

# ----- Injuries - DAILY
# hub.nba.get_team_injuries()
# hub.nba.get_team_injuries(force_date=dt.date(2026, 6, 13))

# ----- Game Schedule - DAILY
# hub.nba.update_past_game_schedule()
# hub.nba.get_next_game_schedule()


# ----- Team Box Scores - DAILY
# hub.nba.get_team_box_score()

# ----- Player Box Scores - DAILY
# hub.nba.get_player_box_score()


# ----- Team Roster - DAILY
# hub.nba.get_team_roster(pre_season=True) # <--- Run this one if updating prior to season
# hub.nba.get_team_roster()


# ---------------------------------- Fantasy Data
# Done manually:
# League matchup dates
# League byes

# ----- League
hub.fty.get_league()


# ----- League Categories
hub.fty.get_league_categories()


# ----- League Competitors
hub.fty.get_league_competitor()


# ----- Free Agents - DAILY
# hub.fty.get_free_agents()


# ----- Competitor Roster - DAILY
# hub.fty.get_competitor_roster()


# ----- Fantasy Matchup
hub.fty.get_league_matchup()


# ----- Matchup box scores - DAILY
# hub.fty.get_matchup_box_score()


# ----- Fantasy Transactions - DAILY
# hub.fty.get_recent_activity()


