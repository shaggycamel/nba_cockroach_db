from dataHub import dataHub

dh = dataHub('postgre')
# dh = dataHub('cockroach')

# ---------------------------------- NBA Data

# ---- Player Season Stats - DONE 2025-26
# dh.get_player_season_stats()


# ----- Player info - DONE 2025-26
# dh.get_player_info()


# ----- Injuries - DAILY
# dh.get_team_injuries()


# ----- Game Schedule - DAILY - DONE 2025-26
# dh.update_past_game_schedule()
# dh.get_next_game_schedule()


# ----- Box Scores - DAILY
# dh.get_box_score()


# ----- Team Roster - DAILY - DONE 2025-26
# Also comprises of updating salaries. Look at player_salaries.py - Eventually coportate this file into dataHub
# dh.get_team_roster(pre_season=True) # <--- Run this one if updating prior to season
# dh.get_team_roster()


# ---------------------------------- Fantasy Data

# ----- League Competitors - DONE 2025-26
# dh.fty_get_league_competitor()


# ----- Free Agents - DAILY
dh.fty_get_free_agents()


# ----- Competitor Roster - DAILY
# dh.fty_get_competitor_roster()


# ----- Fantasy Matchup - DONE 2025-26
# dh.fty_get_league_matchup()


# ----- Fantasy Matchup dates
# dh.fty_get_league_matchup_dates()


# Matchup box scores - DAILY
# dh.fty_get_matchup_box_score()


# ----- Fantasy Transactions - DAILY
# dh.fty_get_recent_activity()


import nbainjuries
import datetime as dt
import zoneinfo
import requests
import polars as pl
import janitor.polars

tz_est = zoneinfo.ZoneInfo('America/New_York')
dt_est = dt.datetime.combine(dt.datetime.now(tz_est).date(), dt.time(0, 0), tzinfo=tz_est)
times = [dt_est + dt.timedelta(minutes=15 * i) for i in range(24 * 4)]
times = [tm.replace(tzinfo=None) for tm in times]
times.reverse()


def get_valid_time():
    for tm in times:
        try:
            nbainjuries._parser.validate_injrepurl(nbainjuries.injury.gen_url(tm))
            return tm
        except (requests.exceptions.HTTPError, Exception) as e:
            continue


df = pl.from_pandas(
    nbainjuries.injury.get_reportdata(get_valid_time(), return_df=True)
).clean_names()

(pl.from_pandas(df).clean_names())

# Use polars to clean and ingest
