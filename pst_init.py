from datetime import date
import pandas as pd
import pro_sports_transactions as pst
import asyncio
import nest_asyncio; nest_asyncio.apply() # needed for running code in jupyter


async def search_transactions(starting_row, transaction_type) -> str:
    return await pst.Search(
        league = pst.League.NBA,
        transaction_types = [transaction_type], # Needs to list, hence []
        start_date = date.fromisoformat("2013-01-01"), # Optional
        end_date = date.today(),
        starting_row = starting_row
    ).get_dict()


# df = asyncio.run(search_transactions()) # use this code when not running in jupyter
df = pd.DataFrame()

pst_page = asyncio.get_event_loop()
for t_t in pst.TransactionType:
    pages = pst_page.run_until_complete(search_transactions(0, t_t))['pages']
    print(t_t.name, '-', pages)
    
    for page in range(pages):
        df_t = pst_page.run_until_complete(search_transactions(page * 25, t_t))
        df_t = pd.DataFrame(df_t['transactions'])
        df_t['transaction_type'] = t_t.name
        df = pd.concat([df, df_t], axis=0, ignore_index=True)

df['acc_req'] = ['Acquired' if len(row[1]['Relinquished'])==0 else 'Relinquished' for row in df.iterrows()]
df['player'] = [row[1]['Acquired'] if len(row[1]['Relinquished'])==0 else row[1]['Relinquished'] for row in df.iterrows()]
df['player'] = df['player'].str.removeprefix('• ')
df.columns = df.columns.str.lower()
df = df[['date', 'transaction_type', 'team', 'player', 'acc_req', 'notes']]

df.to_csv('pst_init.csv', index=False, na_rep=None)