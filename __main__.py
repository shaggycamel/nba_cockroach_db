from sys import argv
from pandas import DataFrame, read_sql_query
from datetime import datetime
from pytz import timezone
from smtplib import SMTP
from sqlalchemy.dialects.postgresql.base import PGDialect; PGDialect._get_server_version_info = lambda * args: (9, 2)
from dataHub import dataHub

dh = dataHub()
# db_con = dh.db_connect('postgre')
db_con = dh.db_connect('cockroach')
fty_con = dh.fty_con(db_con)

print('\nWriting to database:', 'cockroach' if 'cockroach' in str(db_con.url) else 'postgre', '\n\n')


################################## Custom function to handle running & logging events
def custom_prelog(eval_string, table_name, batch_attempt):
    try:
        eval(eval_string)
        success = True  
        error_message = None
    except Exception as e:
        success = False
        error_message = str(e)
        print('--------------------- NOT UPDATED:', table_name, '\n\n')
    finally:
        DataFrame(
            data = {'table_name': table_name, 'process_date': datetime.now(timezone('NZ')), 'batch_attempt': batch_attempt, 'successful_run': success, 'error_message': error_message}, 
            index=[0]
        ).to_sql('update_log', db_con, schema='util', index=False, if_exists='append')


################################### Log start of process
nz_date = datetime.now(timezone('NZ')).strftime('%Y-%m-%d')
batch_attempt = read_sql_query(f"SELECT MAX(batch_attempt) FROM util.update_log WHERE process_date::DATE = '{nz_date}'", db_con)['max']
batch_attempt = 1 if batch_attempt[0] is None else batch_attempt[0] + 1

DataFrame(
    data = {
        'table_name': 'process start', 
        'process_date': datetime.now(timezone('NZ')), 
        'batch_attempt': batch_attempt, 
        'successful_run': True, 
        'error_message': None
    }, 
    index=[0]
).to_sql('update_log', db_con, schema='util', index=False, if_exists='append')


#################################### Obtain update_schedule filtering on US Eastern Time
#################################### Loop through update schedule and update objects accordingly

# Used to be used in SQL query
us_eastern_time = datetime.now(timezone('US/Eastern')).strftime('%Y-%m-%d')

try:
    # this determines if code was run interactively
    if argv[1] != '-f': 
        alt_freq_objs = argv[1].replace(",", "','")
except IndexError as e: pass

if 'alt_freq_objs' in locals(): 
    update_schedule = read_sql_query(f"SELECT * FROM util.update_schedule WHERE table_name IN ('{alt_freq_objs}')", db_con)
else:
    update_schedule = read_sql_query("SELECT * FROM util.update_schedule WHERE pause IS FALSE ORDER BY table_name DESC", db_con)

for _, row in update_schedule.iterrows():
    eval_string = ''.join(['dh.', row['associated_function'], '(', row['function_arguments'], ')'])
    custom_prelog(eval_string, row['table_name'], batch_attempt)
        

#################################### Log end of process
failed_objects = read_sql_query(f"SELECT table_name, error_message FROM util.update_log WHERE successful_run = 'false' AND process_date::DATE = '{nz_date}' AND batch_attempt = {batch_attempt}", db_con)

DataFrame(
    data = {
        'table_name': 'process end', 
        'process_date': datetime.now(timezone('NZ')), 
        'batch_attempt': batch_attempt, 
        'successful_run': False if len(failed_objects) > 0 else True, 
        'error_message': None
    }, 
    index=[0]
).to_sql('update_log', db_con, schema='util', index=False, if_exists='append')


if len(failed_objects) > 0:

    email_address = 'oliverf.eaton@gmail.com'
    password = 'qckbndgopzwjkaxq'
    message = ','.join(failed_objects['table_name'].to_list()) + '\n\n'
    for _, row in failed_objects.iterrows(): message += row['table_name'] + '\n' + row['error_message'] + '\n\n'

    server = SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(email_address, password)
    server.sendmail(email_address, email_address, f'Subject: nba-data-mgmt\n\n{message}')
    raise Exception(print(nz_date, '\nFailed objects:', failed_objects['table_name'].to_list(), '\n'))

else:
    print(nz_date, '\nAll tables successfully updated.')



