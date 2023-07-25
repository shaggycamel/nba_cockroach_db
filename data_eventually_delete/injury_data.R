
# What factors contribute towards a player becoming "injured"?
# Data prep:
# Build off BoxScoreTraditionalV2

# Environ -----------------------------------------------------------------

library(tidyverse)
library(slider)
source(here::here("functions", "fn_data.R"))
source(here::here("data", "useful_objects.R"))
source(here::here("data", "common_data_objects.R"))


# Raw Data ----------------------------------------------------------------

# Expected 148506 rows (148236 with NA removed)
df_Injury <- 
  # Box Score: obtain injured status
  read_df("BoxScoreTraditionalV2.pq") |> 
  select(any_of(cols$id_cols), start_position, comment) |> 
  # Clean start position and play-comments
  mutate(start_flag = start_position != "") |> 
  mutate(
    comment = str_replace(comment, "Inactive", "INV")
    , comment_short = str_extract(comment, "^[:alpha:]{3}")
    , comment = str_remove(comment, comment_short)
    , comment = str_replace_all(comment, "-|_", " ")
    , comment = str_squish(comment)
    , comment = str_to_sentence(comment)
    , comment = str_replace(comment, "Suspended", "League suspension")
    , comment = str_replace(comment, "^Coach$", "Coach's decision")
    , across(starts_with("comment"), ~ case_when(
      start_flag ~ "Started"
      , is.na(comment) ~ "Played"
      , TRUE ~ .x
    ))
  ) |> 
  # Create "injured_flag" for analysis
  mutate(injured_flag = coalesce(str_detect(comment, "Injury"), FALSE)) |> 
  # Bring in player isometric data
  left_join(select(get_PlayerInfo(), player_id = person_id, player_slug, birthdate, height, weight, position)) |>
  mutate(
    height_maj = str_remove(height, "-\\d+")
    , height_min = str_pad(str_remove(height, "\\d-"), 2, "left", "0")
    , height = as.numeric(paste(height_maj, height_min, sep = "."))
    , weight = as.numeric(weight)
  ) |> 
  select(-c(height_maj, height_min)) |> 
  # Bring in team name
  left_join(select(read_df("Teams.pq"), team_id = id, team = full_name)) |> 
  # Bring in game date, matchup & result
  left_join(select(read_df("TeamGameLog.pq"), game_id, team_id, game_date, matchup, wl)) |> 
  mutate(
    game_date = as.Date(game_date, "%b %d, %Y")
    , opponent = str_extract(matchup, "\\w{3}$")
    , wl = if_else(!str_detect(comment_short, "Started|Played"), "No contribution", wl)
  )  |> 
  # Bring in player game log
  left_join(select(read_df("PlayerGameLog.pq"), player_id, game_id, min, reb, ast, stl, blk, tov, pts)) |> 
  # Bring in season_id 
  powerjoin::power_left_join(
    get_Season()
    , by = c(~.x$game_date >= .y$season_start, ~ .x$game_date <= .y$season_end)
    , keep = "left"
  ) |> 
  # Bring in team mgmt
  left_join(get_TeamMgmt()) |> 
  # Lag relevant cols by 1, per season/player
  arrange(season_id, player_id, game_id) |> 
  group_by(season_id, player_id) |> 
  mutate(
    age = game_date - as.Date(birthdate)
    , prev_opponent = coalesce(lag(opponent), "Season start")
    , next_opponent = coalesce(lead(opponent), "Season end")
    , days_since_last_game = coalesce(as.numeric(game_date - lag(game_date)), 0)
    , miss_prev_game = coalesce(!str_detect(lag(comment_short), "Started|Played"), FALSE)
    , start_prev_game = coalesce(str_detect(lag(comment_short), "Started"), FALSE)
    , lag_wl = coalesce(lag(wl), "Season start")
    , lag_min = coalesce(lag(min), 0)
    , lag_reb = coalesce(lag(reb), 0)
    , lag_ast = coalesce(lag(ast), 0)
    , lag_stl = coalesce(lag(stl), 0)
    , lag_blk = coalesce(lag(blk), 0)
    , lag_tov = coalesce(lag(tov), 0)
    , lag_pts = coalesce(lag(pts), 0)
  ) |> 
  ungroup() |> 
  # Drop unnecessary cols | Remove rows with NA somewhere
  select(-c(ends_with(".1"), start_position, matchup, wl, min, reb, ast, stl, blk, tov, pts)) |> 
  na.omit() 
# na omit omitting start_position, thebre removing injureds
  

# Feature Engineering -----------------------------------------------------

#-- season_games_played:     Games played this season
#-- season_play_game_ratio:   Ratio of a players season playing status
#-- season_win_ratio:         The rolling ratio of a players win/loss ratio for a season
#-- season_mins:             Minutes played this season
#-- game_min_diff:         The difference between current and previous mins played
#-- miss_prev_game:          Was the previous game missed
#-- cum_season_mins:
#-- mins_prev_game:
#-- previous_opponent
#-- next_opponent:            Next team to play
# next_opponent_wl_ratio
#-- previous_game_<stat>_ratio
#-- in_prev_start_lineup:     Was player in starting line-up for previous match
#-- age:
#-- days_since_last_game
# off_season_length
# How many times subbed in previous game
# rolling average
# increase decrease in lag vs rolling avg


df_Injury <- df_Injury |> 
  arrange(season_id, player_id, game_id) |> 
  group_by(season_id, player_id) |> 
  # Feature engineering
  mutate(
    game_seq = cumsum(game_id == game_id)
    , season_games_played = cumsum(!miss_prev_game) - 1
    , season_game_play_ratio = coalesce(season_games_played / (cumsum(game_id == game_id) - 1), 0)
    , season_win_ratio = coalesce(cumsum(lag_wl == "W") / (cumsum(game_id == game_id) - 1), 0)
    , season_mins = cumsum(lag_min)
    , .after = comment_short
  ) |> 
  mutate(prev_game_id = coalesce(lag(game_id), "Season start"), .after = game_id) |> 
  # , next_opponent_wl_ratio | Unsure how to do this, but it would be good!
  # , lag_<stat>_prev_game_ratio
  left_join(
    read_df("TeamGameLog.pq") |> 
      group_by(game_id) |> 
      summarise(across(c(reb, ast, stl, blk, tov, pts), ~ sum(.x)), .groups = "drop") |> 
      mutate(min = 48) |> 
      rename(id = game_id) |> 
      rename_with(~ paste0("prev_game_", .x)) |> 
      ungroup()
  ) |> 
  select(-prev_game_id) |>
  mutate(across(starts_with("prev_game"), ~ coalesce(.x, 0))) |> 
  # lag_<stat>_game_ratio
  mutate(
    lag_min_game_ratio = coalesce(lag_min / prev_game_min, 0)
    , lag_reb_game_ratio = coalesce(lag_reb / prev_game_reb, 0)
    , lag_ast_game_ratio = coalesce(lag_ast / prev_game_ast, 0)
    , lag_stl_game_ratio = coalesce(lag_stl / prev_game_stl, 0)
    , lag_blk_game_ratio = coalesce(lag_blk / prev_game_blk, 0)
    , lag_tov_game_ratio = coalesce(lag_tov / prev_game_tov, 0)
    , lag_pts_game_ratio = coalesce(lag_pts / prev_game_pts, 0)
  ) |> 
  # rolling
  mutate(
    roll_min_game = slide_mean(lag_min, before = 10)
    , roll_reb_game = slide_mean(lag_reb, before = 10)
    , roll_ast_game = slide_mean(lag_ast, before = 10)
    , roll_stl_game = slide_mean(lag_stl, before = 10)
    , roll_blk_game = slide_mean(lag_blk, before = 10)
    , roll_tov_game = slide_mean(lag_tov, before = 10)
    , roll_pts_game = slide_mean(lag_pts, before = 10)
  ) |> 
  ungroup()


# Re-align columns -------------------------------------------------------

df_anl <- df_Injury |> 
  select(
    injured_flag
    , comment_short
    , season_id
    , player_id
    , team_id
    , team
    , game_id
    , game_date
    , game_seq
    , player_slug
    , start_flag
    , age
    , height
    , weight
    , position
    , contains("coach")
    , ends_with("opponent")
    , starts_with("season")
    , starts_with("lag")
  ) 

df_anl <- df_anl |>
  semi_join(
    group_by(df_anl, season_id, team_id, player_id) |> 
      summarise(start_count = sum(start_flag)) |> 
      slice_max(start_count, n = 5)
  ) |> 
  # Not much data after game 70, remove for now
  # but why???
  filter(game_seq <= 70)


