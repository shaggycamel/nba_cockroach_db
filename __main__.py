"""Runs the scheduled table updates listed in util.update_schedule.

Usage:
    python __main__.py                      # every table where pause IS FALSE
    python __main__.py daily,intraday       # only these cadences (alt-frequency runs)
    python __main__.py daily intraday       # same; space- or comma-separated
    (interactive consoles: '-f <kernel file>' in argv is ignored)

Configuration lives in the system-wide scs-hub credentials file (the same file
scs-hub reads for its DB and platform credentials). It resolves, in order, from
SCS_HUB_CREDENTIALS or ~/.config/scs_hub_credentials.ini:

    [runtime]
    db_con = cockroach

    [smtp]
    user = alerts@gmail.com
    password = <gmail app password>
    to =

[runtime] db_con names which section of that same file to write to. [smtp] is optional:
without user and password the failure email is skipped, and an empty 'to' sends to 'user'.

Each setting can be overridden by an environment variable, which wins when set: DB_CON,
SMTP_USER, SMTP_PASSWORD, ALERT_TO.

Whitespace around '=' is optional, but note that configparser does not treat '#' after a
value as a comment -- it becomes part of the value. Keep comments on their own lines.

See the configured scs-hub credentials file. In the container it is bind-mounted at
/root/.config/scs_hub_credentials.ini; nothing secret is baked into the image.
"""

import configparser
import logging
import os
import sys
from datetime import datetime
from smtplib import SMTP
from zoneinfo import ZoneInfo

from polars import DataFrame
from scs_hub import SportsHub
from scs_hub.config import credentials_path

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

INI_PATH = credentials_path()
_ini = configparser.ConfigParser()
_ini.read(INI_PATH)  # a missing file is not an error: every lookup then falls through


def setting(env_name, section, key, default=None):
    """Read one setting: environment variable first, then the credentials file.

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

hub = SportsHub(db_con=DB_CON, ini_path=INI_PATH)
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

    # Optional cadence filters; '-f' is ignored (legacy interactive flag)
    # ipykernel (Positron/Jupyter consoles) passes '-f <connection file>' in argv;
    # drop the flag AND its value so the kernel file isn't read as a cadence.
    # Cadences come space- or comma-separated ('daily,intraday' == 'daily intraday'); a bare run
    # means every unpaused row.
    args, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
        elif a == '-f':
            skip = True
        else:
            args.append(a)
    cadences = list(dict.fromkeys(c.strip() for a in args for c in a.split(',') if c.strip()))

    try:
        if cadences:
            # Only the placeholder count is interpolated; the values stay bound.
            placeholders = ', '.join(f':c{i}' for i in range(len(cadences)))
            execute_options = {'parameters': {f'c{i}': c for i, c in enumerate(cadences)}}
            where = f'WHERE cadence IN ({placeholders}) AND pause IS FALSE'
        else:
            execute_options, where = None, 'WHERE pause IS FALSE'
        schedule = hub.db.read(
            'SELECT table_name, associated_function FROM util.update_schedule '
            f'{where} ORDER BY table_name DESC',
            execute_options=execute_options,
        )
    except Exception as e:
        error = f'{type(e).__name__}: {e}'
        log.exception('could not read util.update_schedule')
        log_event('process end', False, error)
        send_alert([('util.update_schedule', error)])
        sys.exit(1)

    log.info('cadences: %s', ', '.join(cadences) if cadences else 'all')
    if schedule.is_empty():
        log.warning('no tables to update for %s', ', '.join(cadences) if cadences else 'all')

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