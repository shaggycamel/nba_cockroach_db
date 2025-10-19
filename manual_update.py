from dataHub import dataHub

dh = dataHub('postgre')
# dh = dataHub('cockroach')


#---------------------------------- NBA Data

#---- Player Season Stats - DONE 2025-26 
# dh.get_player_season_stats()


#----- Player info - DONE 2025-26 
# dh.get_player_info()


#----- Injuries - DAILY
# dh.get_team_injuries()


#----- Game Schedule - REGULARLY - DONE 2025-26 
# Before running this again, check the "season-1" aspect in the call is correct
# dh.update_past_game_schedule(season='current')
# dh.update_past_game_schedule(season='prevoius')
# dh.get_next_game_schedule(update_db=True)


#----- Box Scores - DAILY
# dh.get_box_score()


#----- Team Roster - REGULARLY - DONE 2025-26
# Also comprises of updating salaries. Look at player_salaries.py
# Eventually coportate this file into dataHub
# dh.get_team_roster()



#---------------------------------- Fantasy Data

#----- League Competitors - DONE 2025-26
# dh.fty_get_league_competitor()


#----- Free Agents - DAILY
# dh.fty_get_free_agents()


# ENSURE TO FIX CODE THAT DELETES OLD RECORDS IF UPDATING
# MULTIPLE TIMES IN ONE DAY
#----- Competitor Roster - DAILY
# dh.fty_get_competitor_roster()


#----- Fantasy Matchup - DONE 2025-26
# dh.fty_get_league_matchup()


#----- Fantasy Matchup dates
dh.fty_get_league_matchup_dates()


#----- Fantasy Schedule - CAN DELETE
# dh.fty_get_league_schedule()


# Matchup box scores - DAILY
# dh.fty_get_matchup_box_score()


#----- Fantasy Transactions - DAILY
# dh.fty_get_recent_activity()



# NEED TO RECREATE TEAM_ROSTER_SCHEDULE_VW USING NEW OBJS

from datetime import datetime, timedelta
import pandas as pd

nba_match_dates = []
p_sch = dh.fty_con['ESPN;1966813226'].pro_schedule
for team in p_sch:
    for match_day in p_sch[team]:
        nba_match_dates.append({
            'match_day': int(match_day), 
            'date': datetime.fromtimestamp(p_sch[team][match_day][0]['date'] / 1000).date() - timedelta(days=1) # minus one day to get the conversion right
        })

nba_match_dates = (
    pd.DataFrame(nba_match_dates)
    .drop_duplicates()
    .sort_values('match_day')
)

dh.fty_con['ESPN;95537'].settings.matchup_periods
dh.fty_con['ESPN;95537'].teams[1].schedule[0]._fetch_matchup_info()


espn_matchup_dates = dh.fty_con['ESPN;95537'].matchup_ids
espn_matchup_dates = pd.DataFrame([(int(mp), int(md)) for mp, days in espn_matchup_dates.items() for md in days], columns=['matchup_period', 'match_day'])
espn_matchup_dates = espn_matchup_dates[espn_matchup_dates['match_day'].isin(espn_matchup_dates.groupby('matchup_period')['match_day'].agg(['min','max']).stack())]
espn_matchup_dates = espn_matchup_dates.sort_values(['matchup_period', 'match_day'])
espn_matchup_dates = espn_matchup_dates.merge(nba_match_dates, on = 'match_day', how = 'left')




#NEED TO FIGURE THIS OUT

# Get total number of weeks

total_weeks = dh.fty_con['ESPN;95537'].settings.reg_season_count

# Fetch matchups for every week
all_matchups = []
for week in range(1, total_weeks + 1):
    print(week)
    week_matchups = dh.fty_con['ESPN;95537'].box_scores(scoring_period=8)
    for matchup in week_matchups:
        print(matchup)
        # all_matchups.append({
        #     'week': week,
        #     'home_team': matchup.home_team,
        #     'away_team': matchup.away_team,
        #     'date': matchup.date
        # })

# Print all matchup dates
for m in all_matchups:
    print(f"Week {m['week']}: {m['home_team']} vs {m['away_team']} on {m['date']}")
