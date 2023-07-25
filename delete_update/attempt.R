
# To install packages:
# First navigate to /opt/homebrew/bin
# Secondly, run pip command
library(reticulate)

source_python(here::here("data_eventually_delete", "nba_api_calls", "player_season_stats.py"))
py_run_string("get_player_season_stats('te')")
