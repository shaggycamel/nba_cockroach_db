# To run this file, execute "import yahoo_token_genration" from python console

from pathlib import Path
from yfpy.query import YahooFantasySportsQuery

# Enter correct info
query = YahooFantasySportsQuery(
    league_id="121793",
    game_code="nba",
    yahoo_consumer_key="dj0yJmk9MXpvNlNMZ0VkcVEyJmQ9WVdrOVJYSlplbWxGWWpNbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PTk1",
    yahoo_consumer_secret="72513bb1b0f79425705d32574c29614e110286a0",
)

query.save_access_token_data_to_env_file(
    env_file_location=Path('/Users/fred/git/nba_cockroach_db'), 
    save_json_to_var_only=True
)

# Now look for a file call ".env" in nba_cockroach_db directory