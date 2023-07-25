
def get_player_season_stats(postgres):
    
    # Imports
    from pandas import DataFrame, concat, read_sql_query
    from nba_api.stats.endpoints import playercareerstats
    from nba_api.stats.static import players
    
    
    
    # Parameters
    players = DataFrame(players.get_active_players())['id'].to_list()
    # Change to get_active_players after first run
    
    # # Connect to API and collect data
    print('\n--------------------- player season stats')
    df = DataFrame()
    for player in players:
        player_season = playercareerstats.PlayerCareerStats(player_id=str(player))
        player_season = player_season.data_sets[0].get_data_frame()
        df = concat([df, player_season], ignore_index=True)
        ix = players.index(player)
        if ix % 50 == 0: print('player:', ix, '/', len(players))
    print('player:', ix, '/', len(players))
    # End loop
    # 
    # # Clean up for ingestion into database
    df['PLAYER_ID'] = df['PLAYER_ID'].astype('str')
    df['TEAM_ID'] = df['TEAM_ID'].astype('str')
    df = df.rename(str.lower, axis='columns')
    
    # Combine with existing dataset
    # df_t = read_sql_query('SELECT * FROM nba.player_season_stats', postgres)
    # df = concat([df, df_t], ignore_index=True).drop_duplicates()
    # Uncomment after first run
    
    # Write to database
    # df.to_sql('player_season_stats', postgres, schema='nba', index=False, if_exists='replace')
    print('player_season_stats has been updated')

    return df

