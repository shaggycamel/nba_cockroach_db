"""Runs the scheduled table updates listed in util.update_schedule.

Usage:
    python __main__.py                      # every table where pause IS FALSE
    python __main__.py tbl_a,tbl_b          # only these table_names (alt-frequency runs)
    (interactive consoles: '-f <kernel file>' in argv is ignored)

Configuration lives in credentials.ini, read from the working directory (the same file
sports-hub reads for its DB and platform credentials). Each setting can be overridden by
an environment variable, which wins when set:

    [runtime]
    db_con = cockroach      # DB_CON        section to write to: 'postgres' or 'cockroach'

    [smtp]                  # all optional; without user+password, failure email is skipped
    user = ...              # SMTP_USER     Gmail address alerts are sent from
    password = ...          # SMTP_PASSWORD Gmail app password
    to = ...                # ALERT_TO      recipient, defaults to user

See credentials.ini.example. In the container this file is bind-mounted at
/app/credentials.ini; nothing secret is baked into the image.
"""

import configparser
import logging
import os
import sys
from datetime import datetime
from smtplib import SMTP
from zoneinfo import ZoneInfo

from polars import DataFrame
from sports_hub import SportsHub

try:  # escape hatch: a ./.env still works if you keep one. The image is never given one
    from dotenv import load_dotenv  # (.dockerignore excludes .env*), so this is a no-op there.

    load_dotenv()  # reads ./.env; never overrides variables that are already set
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('nba_cockroach_db')

NZ = ZoneInfo('Pacific/Auckland')

INI_PATH = os.path.join(os.getcwd(), 'credentials.ini')
_ini = configparser.ConfigParser()
_ini.read(INI_PATH)  # a missing file is not an error: every lookup then falls through


def setting(env_name, section, key, default=None):
    """Read one setting: environment variable first, then credentials.ini.

    Env wins so a cron --env-file or os.environ['DB_CON'] = 'postgres' in an
    interactive console can override whatever the ini says.
    """
    return os.environ.get(env_name) or _ini.get(section, key, fallback=default)


DB_CON = setting('DB_CON', 'runtime', 'db_con')
if not DB_CON:
    raise RuntimeError(
        f"No database connection configured. Add a [runtime] section with "
        f"db_con = cockroach (or postgres) to {INI_PATH}, or set DB_CON in the "
        "environment. Either must name a section of that same file."
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
    user = setting('SMTP_USER', 'smtp', 'user')
    password = setting('SMTP_PASSWORD', 'smtp', 'password')
    if not (user and password):
        log.warning('no smtp user/password configured; skipping failure email')
        return

    body = ','.join(t for t, _ in failures) + '\n\n'
    for table, error in failures:
        body += f'{table}\n{error}\n\n'

    # `or user` also covers a present-but-empty 'to =' in the ini
    recipient = setting('ALERT_TO', 'smtp', 'to') or user
    # From/To headers as well as envelope addresses: with only a Subject the mail shows
    # no visible recipient in the client and scores worse with spam filters.
    msg = f'From: {user}\nTo: {recipient}\nSubject: nba-data-mgmt\n\n{body}'

    try:
        with SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, recipient, msg)
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