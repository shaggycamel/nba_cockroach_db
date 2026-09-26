from sports_hub import SportsHub

hub = SportsHub(db_con='postgres', sport='nba')

# Order is deliberate: nba's box scores take their game list from
# league_game_schedule, and fty's matchup box score reads nba.player_box_score.


# ============================ nba ============================================
hub.nba.get_game_schedule()
# hub.nba.get_game_schedule(upcoming_only=True)     # cheap daily refresh
hub.nba.get_player_info()                           # one call per player, ~1s each
# hub.nba.get_team_roster()
hub.nba.get_team_roster(pre_season=True)          # initial load, entry_date left null
hub.nba.get_player_season_stats()                   # one call per player, ~1s each
hub.nba.get_player_box_score()
hub.nba.get_team_box_score()
hub.nba.get_team_injuries()
# hub.nba.get_team_injuries(force_date="2026-09-25")


# ============================ statyx =========================================
hub.statyx.get_schedule()
hub.statyx.get_standings()
hub.statyx.get_game_stats()
hub.statyx.get_advanced_stats()
hub.statyx.get_contracts()                          # no season filter; current year only
hub.statyx.get_player_info()
hub.statyx.get_team_roster()
hub.statyx.get_play_types()
hub.statyx.get_shot_zones()
hub.statyx.get_potential_assists()
hub.statyx.get_usage_shock()
hub.statyx.get_defense_vs_position()
hub.statyx.get_play_type_defense()
hub.statyx.get_shot_zone_defense()

# Statyx returns 500 on these six; re-enable once they fix it
# hub.statyx.get_assist_profile()
# hub.statyx.get_drives()
# hub.statyx.get_matchup_history()
# hub.statyx.get_scoring_breakdown()
# hub.statyx.get_shooting_splits()
# hub.statyx.get_team_assist_defense()


# ============================ fty ============================================
hub.fty.connect_leagues()                           # opens a live session per league
# hub.fty.connect_leagues(season="2024-25")         # backfill another season

hub.fty.get_league()
hub.fty.get_league_categories()
hub.fty.get_league_competitor()
hub.fty.get_league_matchup()
hub.fty.get_competitor_roster()
hub.fty.get_free_agents()
hub.fty.get_recent_activity()
hub.fty.get_matchup_box_score()
hub.fty.get_league_byes()
