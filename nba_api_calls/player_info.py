
def get_player_info(postgres):
    
    # Imports
    from nba_api.stats.endpoints import commonplayerinfo
    from nba_api.stats.static import players
    from pandas import DataFrame, concat
    
    # Parameters
    players = DataFrame(players.get_active_players())['id'].to_list()

    # Connect to API and collect data
    print('\n--------------------- player_info')
    df = DataFrame()
    for player in players:
        
        # Control error here
        player_info = commonplayerinfo.CommonPlayerInfo(player_id=str(player))
        player_info = player_info.data_sets[0].get_data_frame()
        df = concat([df, player_info], ignore_index=True)
        ix = players.index(player)
        if ix % 50 == 0: print('player:', ix, '/', len(players))
    print('player:', ix, '/', len(players))
    # End loop
    
    # Clean up for ingestion into database
    player_info['HEIGHT'] = player_info['HEIGHT'].str.replace('-', '.').astype('float')
    player_info['WEIGHT'] = player_info['WEIGHT'].astype('int')
    df = df.rename(str.lower, axis='columns')
    
    # Write to database
    df.to_sql('player_info', postgres, schema='nba', index=False, if_exists='replace')
    print('player_info has been updated')

