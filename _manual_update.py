from sports_hub import SportsHub
import datetime as dt

hub = SportsHub(db_con = 'postgres')
# hub = SportsHub(db_con = 'cockroach')


# ---------------------------------- NBA Data

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
# Also comprises of updating salaries. Look at player_salaries.py - Eventually coportate this file into dataHub
# hub.nba.get_team_roster(pre_season=True) # <--- Run this one if updating prior to season
# hub.nba.get_team_roster()


# ---------------------------------- Fantasy Data

# ----- League
# hub.fty.get_league()


# ----- League Categories
# hub.fty.get_league_categories()


# ----- League Competitors
# hub.fty.get_league_competitor()


# ----- Free Agents - DAILY
# hub.fty.get_free_agents()


# ----- Competitor Roster - DAILY
# hub.fty.get_competitor_roster()


# ----- Fantasy Matchup
# hub.fty.get_league_matchup()


# ----- Fantasy Matchup dates
# hub.fty.get_league_matchup_dates()


# ----- Matchup box scores - DAILY
# hub.fty.get_matchup_box_score()


# ----- Fantasy Transactions - DAILY
# hub.fty.get_recent_activity()




