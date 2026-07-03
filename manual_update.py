from dataHub import dataHub
import datetime as dt


# dh = dataHub('postgre')
dh = dataHub('cockroach')

# ---------------------------------- NBA Data

# ---- Player Season Stats - DONE 2025-26
# dh.get_player_season_stats()


# ----- Player info - DONE 2025-26
# dh.get_player_info()


# ----- Injuries - DAILY
# dh.get_team_injuries()
# dh.get_team_injuries(force_date=dt.date(2026, 6, 13))


# ----- Game Schedule - DAILY - DONE 2025-26
# dh.update_past_game_schedule()
# dh.get_next_game_schedule()


# ----- Team Box Scores - DAILY
# dh.get_team_box_score()

# ----- Player Box Scores - DAILY
# dh.get_player_box_score()


# ----- Team Roster - DAILY - DONE 2025-26
# Also comprises of updating salaries. Look at player_salaries.py - Eventually coportate this file into dataHub
# dh.get_team_roster(pre_season=True) # <--- Run this one if updating prior to season
# dh.get_team_roster()


# ---------------------------------- Fantasy Data

# ----- League Competitors - DONE 2025-26
# dh.fty_get_league_competitor()


# ----- Free Agents - DAILY
# dh.fty_get_free_agents()


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


import polars as pl
import polars.selectors as cs
import nba_api.stats.endpoints as nba_ep
import nbainjuries
import dateutil
import requests


request = requests.get('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json')
key_dates = pl.read_database('SELECT * FROM nba.key_dates', dh.db_con)
col_order = pl.read_database(
    "SELECT column_name FROM util.table_column_order WHERE table_name = 'league_game_schedule' ORDER BY column_order",
    dh.db_con,
)['column_name'].to_list()

# Remove games already played this season - This assumes update_past_game_schedule is run first
df_played_games = pl.read_database(
    f"SELECT * FROM nba.league_game_schedule WHERE season = '{dh.cur_season}' AND team_winner IS NOT NULL",
    dh.db_con,
)

dfs = []
for game_date in request.json()['leagueSchedule']['gameDates']:
    for game in game_date['games']:
        dfs.append(
            {
                'game_id': int(game['gameId']),
                'game_date': dateutil.parser.parse(game_date['gameDate']).date(),
                'matchup': game['homeTeam']['teamTricode']
                + ' vs. '
                + game['awayTeam']['teamTricode'],
            }
        )

df = (
    pl.concat(
        [
            pl.DataFrame(dfs),
            (
                pl.DataFrame(dfs)
                .with_columns(pl.col('matchup').str.split_exact(' ', n=2))
                .unnest(pl.col('matchup'))
                .with_columns(
                    (pl.col('field_2') + ' @ ' + pl.col('field_0'))
                    .str.strip_chars()
                    .alias('matchup')
                )
                .drop(cs.starts_with('field'))
            ),
        ]
    )
    .with_columns(pl.col('matchup').str.split_exact(' ', n=2).alias('temp'))
    .unnest(pl.col('temp'))
    .with_columns(
        [
            pl.lit(self.cur_season).alias('season'),
            pl.lit(None).alias('team_winner'),
            pl.lit(None).alias('team_loser'),
            pl.col('field_0').alias('team'),
            pl.col('field_2').alias('opponent'),
            pl.when(pl.col('field_1') == 'vs.')
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias('home'),
        ]
    )
    .with_columns(
        [
            pl.when(pl.col('matchup').str.strip_chars().is_in(['@', 'vs.']))
            .then(pl.lit('undetermined') if col == 'matchup' else pl.lit(None))
            .otherwise(pl.col(col))
            .alias(col)
            for col in ['team', 'opponent', 'matchup']
        ]
    )
    .join_where(
        key_dates,
        pl.col('game_date') >= pl.col('begin_date'),
        pl.col('game_date') <= pl.col('end_date'),
    )
    .select(col_order)
    .join(
        df_played_games.select('game_id').with_columns(pl.col('game_id').cast(pl.Int64)),
        on='game_id',
        how='anti',
    )
    .filter(
        pl.col('team').is_in(self.nba_teams.get_column('abbreviation').to_list())
        | pl.col('opponent').is_in(self.nba_teams.get_column('abbreviation').to_list())
        | (pl.col('matchup') == 'undetermined')
    )
)

# Write to database
df.to_pandas().to_sql(
    'league_game_schedule', self.db_con, schema='nba', index=False, if_exists='append'
)
print('nba.current_game_schedule has been updated\n\n')
