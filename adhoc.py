import pandas as pd
from dataHub import dataHub
from nba_api import stats

dh = dataHub('postgre')

dfs1 = stats.endpoints.boxscoreadvancedv2.BoxScoreAdvancedV2(game_id='0022401114')
dfs2 = stats.endpoints.boxscoretraditionalv2.BoxScoreTraditionalV2(game_id='0022401114')

