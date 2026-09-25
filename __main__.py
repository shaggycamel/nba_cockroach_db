"""Runs the scheduled table updates listed in util.update_schedule.

Usage:
    python __main__.py                      # every table where pause IS FALSE
    python __main__.py tbl_a,tbl_b          # only these table_names (alt-frequency runs)
    (interactive consoles: '-f <kernel file>' in argv is ignored)

Environment:
    DB_CON         credentials.ini section to write to: 'postgres' or 'cockroach' (required)
    SMTP_USER      Gmail address used to send failure alerts (optional)
    SMTP_PASSWORD  Gmail app password (optional)
    ALERT_TO       alert recipient, defaults to SMTP_USER (optional)

credentials.ini is read from the working directory by sports-hub.
"""

import logging
import os
import sys
from datetime import datetime
from smtplib import SMTP
from zoneinfo import ZoneInfo

from polars import DataFrame
from sports_hub import SportsHub

try:  # dev-only convenience: python-dotenv isn't installed in the image
    from dotenv import load_dotenv

    load_dotenv()  # reads ./.env; never overrides variables that are already set
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('nba_cockroach_db')

NZ = ZoneInfo('Pacific/Auckland')
DB_CON = os.environ.get('DB_CON')
if not DB_CON:
    raise RuntimeError(
        "DB_CON is not set. Set it to a credentials.ini section, e.g. "
        "DB_CON=cockroach in the shell, or os.environ['DB_CON'] = 'postgres' "
        "in an interactive session before running this."
    )

hub = SportsHub(db_con=DB_CON)
log.info('Writing to database: %s', DB_CON)


log_write_errors = []


def log_event(table_name, success, error=None):
    """Write one row to util.update_log. A failed write doesn't stop the run,
    but it is recorded and makes the run exit non-zero and send an alert."""
    try:
        df = DataFrame(
            {
                'table_name': table_name,
                'process_date': datetime.now(NZ),
                'successful_run': success,
                'error_message': error,
            }
        )
        hub.db.write(df, 'update_log', 'util')
    except Exception as e:
        log.exception('could not write update_log row for %s', table_name)
        log_write_errors.append(str(e))


def resolve(dotted_path):
    """'nba.get_team_box_score' -> hub.nba.get_team_box_score"""
    obj = hub
    for part in dotted_path.split('.'):
        obj = getattr(obj, part)
    return obj


def connect_leagues():
    """Fantasy methods dispatch over connected leagues, so connect them first."""
    qry = f"""
        select lg.*, pf.credentials
        from fty.customer_league as lg
        left join fty.customer_platform as pf on lg.customer_id = pf.customer_id
            and lg.platform = pf.platform
        where season = '{hub.ctx.cur_season}'
    """
    leagues = hub.db.read(qry).group_by('league_id').first(ignore_nulls=True)
    hub.fty.connect_leagues(leagues=leagues)


def send_alert(failures):
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')
    if not (user and password):
        log.warning('SMTP_USER / SMTP_PASSWORD not set; skipping failure email')
        return

    body = ','.join(t for t, _ in failures) + '\n\n'
    for table, error in failures:
        body += f'{table}\n{error}\n\n'

    try:
        with SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, os.environ.get('ALERT_TO', user), f'Subject: nba-data-mgmt\n\n{body}')
    except Exception:
        log.exception('could not send failure email')


def main():
    log_event('process start', True)

    # Optional table_name overrides; '-f' is ignored (legacy interactive flag)
    # ipykernel (Positron/Jupyter consoles) passes '-f <connection file>' in argv;
    # drop the flag AND its value so the kernel file isn't read as a table name.
    args, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
        elif a == '-f':
            skip = True
        else:
            args.append(a)
    try:
        if args:
            names = [n.strip().replace("'", "''") for n in ','.join(args).split(',') if n.strip()]
            quoted = ','.join(f"'{n}'" for n in names)
            schedule = hub.db.read(
                f'SELECT table_name, associated_function FROM util.update_schedule WHERE table_name IN ({quoted})'
            )
        else:
            schedule = hub.db.read(
                'SELECT table_name, associated_function FROM util.update_schedule '
                'WHERE pause IS FALSE ORDER BY table_name DESC'
            )
    except Exception as e:
        error = f'{type(e).__name__}: {e}'
        log.exception('could not read util.update_schedule')
        log_event('process end', False, error)
        send_alert([('util.update_schedule', error)])
        sys.exit(1)

    failures = []

    def run(table_name, fn):
        try:
            log.info('starting: %s', table_name)
            fn()
        except Exception as e:
            error = f'{type(e).__name__}: {e}'
            log.exception('NOT UPDATED: %s', table_name)
            failures.append((table_name, error))
            log_event(table_name, False, error)
        else:
            log.info('finished: %s', table_name)
            log_event(table_name, True)

    # connect_leagues isn't a table, so it gets no update_log row of its own;
    # a failure still counts towards the alert, exit code and 'process end' row.
    if any(f.startswith('fty.') for f in schedule['associated_function']):
        try:
            connect_leagues()
        except Exception as e:
            log.exception('could not connect leagues')
            failures.append(('connect_leagues', f'{type(e).__name__}: {e}'))

    for row in schedule.iter_rows(named=True):
        run(row['table_name'], lambda f=row['associated_function']: resolve(f)())

    log_event('process end', len(failures) == 0)

    if log_write_errors:
        failures.append(
            ('util.update_log', f'{len(log_write_errors)} log write(s) failed; first error: {log_write_errors[0]}')
        )

    if failures:
        send_alert(failures)
        log.error('failed objects: %s', [t for t, _ in failures])
        sys.exit(1)

    log.info('all tables successfully updated')

if __name__ == '__main__':
    main()