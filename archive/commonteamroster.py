from nba_api.stats.endpoints import commonteamroster

print('\n--------------------- commonteamroster')
df = pd.DataFrame()
for i in range(0, len(nba_teams)):
    for y in range(max_season-4, max_season+1):
        common_teamroster = commonteamroster.CommonTeamRoster(
            team_id=str(nba_teams[i]['id'])
            , season=y
            , timeout=timeout
        )
        p = common_teamroster.data_sets[1].get_data_frame()
        df = pd.concat([df, p], ignore_index=True)
    if i % 5 == 0 and y == max_season: print('team:', i, '/', len(nba_teams))
print('team:', i, '/', len(nba_teams))
    

df.to_parquet('.parquet/CoachTeamRoster.pq')
print('\n')