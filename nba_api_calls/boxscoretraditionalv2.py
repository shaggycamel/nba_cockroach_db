from nba_api.stats.endpoints import boxscoretraditionalv2

#----------------------------------------------------------------------------------
# Sometimes had to split running this code, because api connection would time out

print('\n--------------------- boxscoretraditionalv2')
nba_games = (pd.read_parquet('.parquet/TeamGameLog.pq')['Game_ID']
             .drop_duplicates().reset_index(drop=True))

## new index
## df.to_parquet('.parquet/boxscoretraditionalv2.pq')
# df = pd.read_parquet('.parquet/boxscoretraditionalv2.pq')
# ix = df.tail(1)['GAME_ID']
# ix = nba_games[nba_games == list(ix)[0]].index[0] + 1

## write to pq
# df_t = pd.read_parquet('.parquet/GameRotation.pq')
# df = pd.concat([df_t, df], ignore_index=True).drop_duplicates().reset_index(drop=True)
# df.to_parquet('.parquet/boxscoretraditionalv2.pq')


df = pd.DataFrame()
# df = pd.read_parquet('.parquet/GameRotation.pq')
for i in range(0, len(nba_games)):
# for i in range(ix, len(nba_games)):
    boxscore_trad = boxscoretraditionalv2.BoxScoreTraditionalV2(
        game_id = nba_games[i]
        , timeout=timeout
    )
    p = boxscore_trad.data_sets[0].get_data_frame()
    df = pd.concat([df, p], ignore_index=True)
    if i % 25 == 0: print('game:', i, '/', len(nba_games))
print('game:', i, '/', len(nba_games))
    
df.to_parquet('.parquet/boxscoretraditionalv2.pq')
print('\n')