from nba_api.stats.endpoints import teamgamelog

print('\n--------------------- teamgamelog')
df = pd.DataFrame()
for i in range(0, len(nba_teams)):
    for y in range(max_season-4, max_season+1):
        team_gamelog = teamgamelog.TeamGameLog(
            team_id=str(nba_teams[i]['id'])
            , season=y
            , season_type_all_star='Regular Season'
            , timeout=timeout
        )
        p = team_gamelog.data_sets[0].get_data_frame()
        df = pd.concat([df, p], ignore_index=True)
    if i % 5 == 0: print('team:', i, '/', len(nba_teams))
print('team:', i, '/', len(nba_teams))
    
df.to_parquet('.parquet/TeamGameLog.pq')
print('\n')