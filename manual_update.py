from dataHub import dataHub

# dh = dataHub('postgre')
dh = dataHub('cockroach')


#---------------------------------- NBA Data

#---- Player Season Stats - DONE 2025-26 
# dh.get_player_season_stats()


#----- Player info - DONE 2025-26 
# dh.get_player_info()


#----- Injuries - DAILY
# dh.get_team_injuries()


#----- Game Schedule - DAILY - DONE 2025-26 
# dh.update_past_game_schedule()
# dh.get_next_game_schedule()


#----- Box Scores - DAILY
dh.get_box_score()


#----- Team Roster - REGULARLY - DONE 2025-26
# Also comprises of updating salaries. Look at player_salaries.py
# Eventually coportate this file into dataHub
# dh.get_team_roster()



#---------------------------------- Fantasy Data

#----- League Competitors - DONE 2025-26
# dh.fty_get_league_competitor()


#----- Free Agents - DAILY
# dh.fty_get_free_agents()


#----- Competitor Roster - DAILY
# dh.fty_get_competitor_roster()


#----- Fantasy Matchup - DONE 2025-26
# dh.fty_get_league_matchup()


#----- Fantasy Matchup dates
# dh.fty_get_league_matchup_dates()


# Matchup box scores - DAILY
# dh.fty_get_matchup_box_score()


#----- Fantasy Transactions - DAILY
# dh.fty_get_recent_activity()


