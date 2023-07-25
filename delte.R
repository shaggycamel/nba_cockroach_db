
cock <- ini::read.ini(here::here("database.ini"))$cockroach

cockroach_con <- DBI::dbConnect(
  drv = RPostgres::Postgres(),
  user = cock$user,
  host = cock$host,
  port = cock$port,
  password = cock$password,
  dbname = cock$database
  # options="-c search_path=nba"
)

x <- DBI::dbGetQuery(cockroach_con, "SELECT * FROM nba.player_game_log")
DBI::dbWriteTable(cockroach_con, Id(schema = "util", table = "fty_nba_id_matchup"), x)

DBI::dbExecute(cockroach_con, 'DROP TABLE nba.fty_nba_id_matchup')

