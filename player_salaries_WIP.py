import requests
import pandas as pd
from bs4 import BeautifulSoup

ls = [] # eventually move to inner
url = "https://www.basketball-reference.com/contracts/players.html#player-contracts"
    
# Send GET request
response = requests.get(url)
soup = BeautifulSoup(response.content, "html.parser")

# Find the salary table rows
rows = soup.select("table tbody tr")

# WORK IN PROGRESS

for row in rows:
    elements = row.find_all("td")
    name = elements[1].text.strip()
    # salary = pd.to_numeric(elements[2].get("data-value"))
    # ls.append({'season': season, 'name': name, 'salary': salary})
    print(elements)

df = pd.DataFrame(ls) # eventually bring in player id and join onto nba.roster table




# TEMP SOLUTION

from dataHub import dataHub
import pandas as pd
import difflib

dh = dataHub('postgre')

df_salary = pd.read_csv('basketball_reference_salaries.csv')
df_salary = df_salary[['Player', '2025-26']]
df_salary = df_salary.rename({'2025-26':'salary', 'Player':'player'}, axis = 'columns')
df_salary['salary'] = [float(el.replace('$', '')) for el in df_salary['salary']]


df_player_id = pd.read_sql("SELECT season, team_slug, player_id, player FROM nba.team_roster WHERE season = '2025-26'", dh.db_con)
df_player_id = df_player_id.merge(df_salary, on='player', how='left')

df_player_id_notna = df_player_id[df_player_id['salary'].notna()]
df_player_id_na = df_player_id[df_player_id['salary'].isna()]
df_player_id_na = pd.read_clipboard()
df_player_id = pd.concat([df_player_id_notna, df_player_id_na])

df_player_id['salary'] = [float(el.replace('$', '')) for el in df_player_id['salary']]

for _, row in df_player_id.iterrows():
    if pd.notna(row['salary']):
        print(f"UPDATE nba.TEAM_ROSTER SET salary = {row['salary']} WHERE season = '2025-26' AND player_id = {row['player_id']};")
