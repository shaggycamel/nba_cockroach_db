from polars_conversion import dataHub
import polars as pl
import janitor.polars
import nba_api.stats.endpoints as nba_ep

dh = dataHub('cockroach')


# up to injuries