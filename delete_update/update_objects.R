
library(tidyverse)
library(nbastatR)
library(here)
library(snakecase)
library(DBI)
source(here("data_hub.R"))


# Constants ---------------------------------------------------------------

current_season <- 2024


# player_game_log** ---------------------------------------------------------
# Update schedule: daily
# Update instructions:
  # request only latest season
  # union with existing database table
  # drop duplicates

og_player_game_log <- dh_getQuery(postgre_nba_con, "SELECT * FROM nba.player_game_log")

player_game_log <- 
  map_dfr(current_season, ~{
    game_logs(
      seasons = .x,
      season_types = c("Regular Season", "Playoffs", "Pre Season", "All Star"),
      assign_to_environment = FALSE
    )
  }) |> 
  select(-starts_with("url")) |> 
  rename_with(to_snake_case) |> 
  bind_rows(og_player_game_log) |> 
  group_by(year_season, id_game, id_player) |> 
  slice_max(order_by = is_b2b, with_ties = FALSE)

DBI::dbAppendTable()

# Residual object created for some reason
rm(df_nba_player_dict, og_player_game_log)


# league_game_schedule** ----------------------------------------------------

# Update schedule using current_schedule() function:
  # beginning of season
  # beginning of playoffs
# Update instructions:
  # request only latest season
  # union with existing database table
  # drop duplicates
league_game_schedule <- 
  map_dfr(current_season, ~ {
    seasons_schedule(
      seasons = .x,
      season_types = c("Regular Season", "Playoffs", "Pre Season", "All Star")
    )
  }) |> 
  select(-starts_with("url")) |> 
  rename_with(to_snake_case)


# player_info** -------------------------------------------------------------

# Update schedule:
  # beginning of season
# Update instructions:
  # combine with existing player_info table
  # groupby playerId
  # slice_max on lastSeason
  # drop duplicates


safe_func <- safely(\(x) player_profiles(player_ids = x), quiet = FALSE)

player_info_x <- 
  p_data$idPlayer |> # ids of new and existing players (exclude old players)
  map(~ safe_func(.x)) |> 
  select(-starts_with("url")) |>
  rename_with(to_snake_case)


# player_season_stats** -----------------------------------------------------

# Update schedule:
  # weekly (during season)
# Update instructions:
  # request only latest season
  # union with existing database table
  # groupby player_id, season
  # slice max
  # drop duplicates
player_season_stats <- 
  map_dfr(current_season, ~{
    bref_players_stats(
      seasons = .x,
      tables = "totals",
      assign_to_environment = FALSE
    )
  }) |> 
  select(-starts_with("url")) |> 
  rename_with(to_snake_case)


# teams** -------------------------------------------------------------------

# Update schedule:
  # Only once
  # There forward, only if a franchise changes
# Update instructions (if franchise changes):
  # replace existing database table
teams <- nba_teams_seasons() |>
  rename_with(to_snake_case)


# team_roster -------------------------------------------------------------

# Update schedule:
  # beginning of season
  # after mid-season trades
# Update instructions:
  # request only latest season
  # union with existing database table
  # drop duplicates
  # if player has been traded, flag old record for corresponding season
team_roster <- 
  # update with years manually
  map_dfr(current_season, ~ teams_rosters(seasons = .x)) |>
  rename_with(to_snake_case)

# tag players with original team prior trade before ingest
# Only need to do this once (if tables remain being updated correctly)
traded <- filter(team_roster, str_detect(how_acquired, "^Trade")) |> 
  mutate(old_team = str_trim(str_extract(how_acquired, " \\w{3} "))) |>
  left_join(select(teams, old_id_team=id_team, slug_team), c("old_team"="slug_team")) |> 
  left_join(distinct(select(team_roster, old_name_team=name_team, id_team)), c("old_id_team"="id_team")) |> 
  mutate(name_team = old_name_team, id_team = old_id_team, how_acquired=NA) |> 
  select(-starts_with("old"))

team_roster <- bind_rows(team_roster, traded) |> 
  arrange(year_season, id_team, name_player)


# injuries** ----------------------------------------------------------------

# Update schedule:
  # daily (during season)
# Update instructions:
  # union with existing database table
  # drop duplicates
injuries <- 
  bref_injuries() |> 
  rename_with(to_snake_case)



# UPLOAD ------------------------------------------------------------------

# league_game_schedule
# player_game_log
# player_info
# player_season_stats
# teams
# injuries
# team_roster

# dbWriteTable(postgre_con, "team_roster", team_roster, overwrite = TRUE)
