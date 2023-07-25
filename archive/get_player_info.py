
from pandas import DataFrame

def fty_get_player_info(self, players, postgres):

    df = []
    for player in players:
        df.append({
            'player_id': player.playerId,
            'player_name': player.name,
            'player_team': player.proTeam,
            'player_status': player.injuryStatus,
            'player_position': player.position
        }) 

    # Clean in prep for database ingestion
    df = DataFrame(df)
    df['player_id'] = df['player_id'].astype('str')