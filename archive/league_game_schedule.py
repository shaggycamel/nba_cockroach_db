
def get_league_game_schedule(postgres):

    from requests import get
    from nba_api.stats.library.parameters import Season
    from pandas import DataFrame, concat, to_datetime, read_sql_query

    # data request
    request = get(f'https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/{Season.current_season_year}/league/00_full_schedule_week_tbds.json')

    # Dataframe object to be added to
    df = DataFrame()
    
    # Loop through month elements
    for month in request.json()['lscd']:
        df_row = DataFrame(month['mscd']['g'])[['gid', 'gdte', 'an', 'ac', 'htm', 'vtm', 'v', 'h']]

        # Obtain home and away team info
        for col in ['h', 'v']:
            df_col = DataFrame([[el['tid'], el['ta']] for el in df_row[col]])
            df_col.columns = ['home_team_id', 'home_team_slug'] if col == 'h' else ['away_team_id', 'away_team_slug']
            df_row = concat([df_row, df_col], axis = 1)

        # Rename columns
        df_row = df_row.drop(columns=['v', 'h'])
        df_row = df_row.rename(columns={'gid':'game_id', 'gdte':'game_date', 'an':'arena', 'ac':'city', 'htm':'home_team_time', 'vtm':'away_team_time'})

        # Collate data
        df = concat([df, df_row], ignore_index=True)

    # Cast date columns to_date
    df[['game_date', 'home_team_time', 'away_team_time']] = df[['game_date', 'home_team_time', 'away_team_time']].apply(to_datetime)

    # Combine with existing dataset
    df_t = read_sql_query('SELECT * FROM nba.league_game_schedule', postgres)
    df = concat([df, df_t], ignore_index=True).drop_duplicates()

    # Write to database
    df.to_sql('league_game_schedule', postgres, schema='nba', index=False, if_exists='replace')
    print('league_game_schedule has been updated')