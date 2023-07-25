from nba_api.stats.endpoints import gamerotation

print('\n--------------------- gamerotation')
nba_games = (pd.read_parquet('.parquet/TeamGameLog.pq')['Game_ID']
             .drop_duplicates().reset_index(drop=True))

df = pd.DataFrame()
for i in range(0, len(nba_games)):
# for i in range(ix, len(nba_games)):
    game_rotation = gamerotation.GameRotation(game_id=nba_games[i], league_id='00', timeout=timeout)
    h_team = game_rotation.data_sets[0].get_data_frame().assign(home_away = 'home')
    a_team = game_rotation.data_sets[1].get_data_frame().assign(home_away = 'away')
    p = pd.concat([h_team, a_team], ignore_index=True)
    p.insert(3, 'home_away', p.pop('home_away'))
    df = pd.concat([df, p], ignore_index=True)
    if i % 5 == 0: print('game:', i, '/', len(nba_games))
print('game:', i, '/', len(nba_games))
    
df.to_parquet('.parquet/GameRotation.pq')

#----------------------------------------------------------------------------------
# Sometimes had to split running this code, because api connection would time out

# new index
## df = pd.read_parquet('.parquet/GameRotation.pq')
# ix = df.tail(1)['GAME_ID']
# ix = nba_games[nba_games == list(ix)[0]].index[0] + 1

# write to pq
# df_t = pd.read_parquet('.parquet/GameRotation.pq')
# df = pd.concat([df_t, df], ignore_index=True).drop_duplicates().reset_index(drop=True)
# df.to_parquet('.parquet/GameRotation.pq')

print('\n')