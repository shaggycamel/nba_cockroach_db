
db_info <- ini::read.ini(here::here("database.ini"))

postgre_nba_con <- DBI::dbConnect(
  drv = RPostgres::Postgres(),
  user = db_info$postgre$user,
  host = db_info$postgre$host,
  port = db_info$postgre$port,
  password = db_info$postgre$password,
  dbname = db_info$postgre$database,
  options="-c search_path=nba"
)

postgre_fty_con <- DBI::dbConnect(
  drv = RPostgres::Postgres(),
  user = db_info$postgre$user,
  host = db_info$postgre$host,
  port = db_info$postgre$port,
  password = db_info$postgre$password,
  dbname = db_info$postgre$database,
  options="-c search_path=fty"
)

cockroach_con <- DBI::dbConnect(
  drv = RPostgres::Postgres(),
  user = db_info$cockroach$user,
  host = db_info$cockroach$host,
  port = db_info$cockroach$port,
  password = db_info$cockroach$password,
  dbname = db_info$cockroach$database
)


dh_getQuery <- function(connection, query){
  
  query <- if(grepl("^SELECT ", query)) query
    else readr::read_file(query)
  
  tibble::as_tibble(DBI::dbGetQuery(connection, query)) |>
    dplyr::mutate(dplyr::across(where(~ class(.x) == "integer64"), ~ as.integer(.x)))
  
}

rm(db_info)