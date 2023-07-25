def get_player_game_log(postgres):
    
    # Imports
    from datetime import datetime, date, timedelta
    from pandas import DataFrame, concat, to_datetime, read_sql_query
    from nba_api.stats.endpoints import playergamelog
    from nba_api.stats.static import players
    
    # Parameters
    players = DataFrame(players.get_active_players())['id'].to_list()
    date_from = read_sql_query('SELECT MAX(game_date) FROM nba.player_game_log', postgres)['max'][0]
    date_from = (date_from + timedelta(days=1)).strftime('%m/%d/%Y')
    date_to = (date.today() - timedelta(days=2)).strftime('%m/%d/%Y')

    # Connect to API and collect data
    print('\n--------------------- player_game_log')
    df = DataFrame() 
    for player in players:
        
        player_game_log = playergamelog.PlayerGameLog(
            player_id=str(player), 
            date_from_nullable=date_from, 
            date_to_nullable=date_to
        )
        
        player_game_log = player_game_log.data_sets[0].get_data_frame()
        df = concat([df, player_game_log], ignore_index=True)
        ix = players.index(player)
        if ix % 50 == 0: print('player:', ix, '/', len(players))
    print('player:', ix, '/', len(players))
    # End loop
        
    # Clean up for ingestion into database
    df['GAME_DATE'] = to_datetime(df['GAME_DATE'])
    df = df.rename(str.lower, axis='columns')
    
    # Write to database
    df.to_sql('player_game_log', postgres, schema='nba', index=False, if_exists='append')
    print('player_game_log has been updated to:', datetime.strptime(date_to, '%m/%d/%Y').strftime('%Y-%m-%d'))

