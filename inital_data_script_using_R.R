
library(tidyverse)
library(nbastatR)
library(here)
library(snakecase)
source(here("data", "dataHub.R"))


# player_game_log** ---------------------------------------------------------

# Update schedule:
  # daily
# Update instructions:
  # request only latest season
  # union with existing database table
  # drop duplicates
player_game_log <- 
  map_dfr(2010:2023, ~{
    game_logs(
      seasons = .x,
      season_types = c("Regular Season", "Playoffs", "Pre Season", "All Star"),
      assign_to_environment = FALSE
    )
  }) |> 
  select(-starts_with("url")) |> 
  rename_with(to_snake_case)


# league_game_schedule** ----------------------------------------------------

# Update schedule using current_schedule() function:
  # beginning of season
  # beginning of playoffs
# Update instructions:
  # request only latest season
  # union with existing database table
  # drop duplicates
league_game_schedule <- 
  map_dfr(2010:2023, ~ {
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
# error_players <- c("Jeff Adrien", "David Andersen","Gustavo Ayon", "Ibou Badji", "Amari Bailey", "Ernie Barrett")
safe_func <- safely(\(x) player_profiles(player_ids = x), quiet = FALSE)
p_data <- janitor::remove_empty(nba_players()[4501:5000, ], which = "rows")

player_info_x <- 
  p_data$idPlayer |> 
  map(~ safe_func(.x))

# player_info_ls <- player_info_x
# player_info_ls <- append(player_info_ls, player_info_x)

# player_info_x <- map_dfr(player_info_ls[1:5000], ~ .x[["result"]])
# err_players <- setdiff(nba_players()$idPlayer, player_info_x$idPlayer)
# 
# player_info <- 
#   filter(nba_players(), idPlayer %in% err_players) |> 
#   select(any_of(names(player_info_x))) |> 
#   bind_rows(player_info_x) |> 
#   select(-starts_with("url")) |>
#   rename_with(to_snake_case)


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
  map_dfr(2010:2023, ~{
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
team_roster_x <- 
  # update with years manually
  map_dfr(2010:2023, ~ teams_rosters(seasons = .x)) |>
  rename_with(to_snake_case)

# team_roster <- team_roster_x
team_roster <- bind_rows(team_roster, team_roster_x)

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
