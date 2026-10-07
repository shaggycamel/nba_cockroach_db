# nba_cockroach_db

Scheduled table updates for the NBA / fantasy database.

`__main__.py` reads `util.update_schedule`, calls each row's `associated_function` on a
[sports-hub](https://github.com/shaggycamel/sports-hub) `SportsHub`, writes one row per
table to `util.update_log`, emails any failures, and exits non-zero if anything failed.

```
python __main__.py                 # every table where pause IS FALSE
python __main__.py daily,6h        # only rows whose cadence is one of these
python __main__.py daily 6h        # same; space- or comma-separated
```

Each row's `cadence` names the run it belongs to: `./cron.sh daily` picks up every
unpaused row with `cadence = 'daily'`, and a bare `./cron.sh` ignores cadence entirely.
Rows run once each, in a single `ORDER BY table_name DESC`, with no per-cadence grouping.

It runs as a Docker container, once per cron job, on a single always-on host (the NUC).

## Configuration

Everything lives in one system-wide file, `~/.config/sports-hub-credentials.ini` — the same
file sports-hub reads for its DB and platform credentials. Set `SPORTS_HUB_CREDENTIALS` to
point at a different path instead; both `__main__.py` and sports-hub honour it. Create the
file `chmod 600` and never commit it (it lives outside the repo).

It holds the DB/platform sections sports-hub expects (`[cockroach]`/`[postgres]`,
`[statyx]`, `[espn_api]`, `[yahoo_api]`) plus this repo's `[runtime]` and `[smtp]` sections.

A direct `python __main__.py` reads the same file, so no `cd` or working-directory setup is
needed.

| Section    | Key        | Env override    | Purpose                                     |
| ---------- | ---------- | --------------- | ------------------------------------------- |
| `[runtime]`| `db_con`   | `DB_CON`        | which DB section to write to                |
| `[smtp]`   | `user`     | `SMTP_USER`     | Gmail address failure alerts are sent from  |
| `[smtp]`   | `password` | `SMTP_PASSWORD` | Gmail app password                          |
| `[smtp]`   | `to`       | `ALERT_TO`      | recipient; defaults to `user`               |

Environment variables win when set, so `os.environ['DB_CON'] = 'postgres'` still works in
an interactive console. Without `[smtp] user` + `password` the failure email is skipped
and the run simply exits 1.

The local `~/.config` file should point at `[runtime] db_con = postgres` so a stray local
run cannot write to cockroach.

## Deploying to the NUC

The image is built on the NUC itself — native amd64, no registry, and no credentials ever
leave the box.

```bash
# 1. one-off: the system-wide config file
mkdir -p ~/.config
$EDITOR ~/.config/sports-hub-credentials.ini   # real creds, db_con = cockroach
chmod 600 ~/.config/sports-hub-credentials.ini

# 2. build (repeat after every git pull)
cd ~/git/nba_cockroach_db && git pull
docker build -t nba_cockroach_db:latest .

# 3. run
./cron.sh                  # all unpaused tables
./cron.sh daily,6h         # only those cadences
```

`cron.sh` bind-mounts the config read-only at `/root/.config/sports-hub-credentials.ini`,
so nothing secret is in the image. It keeps the container after the run (no `--rm`) so
`docker logs update_tables` works until the next run, and it propagates the exit status.

Crontab — cron has no `PATH`, which is why `cron.sh` sets one:

```cron
0  3 * * *  /home/oli/github/nba_cockroach_db/cron.sh daily >> /home/oli/github/nba_cockroach_db/cron.log 2>&1
0 */6 * * * /home/oli/github/nba_cockroach_db/cron.sh 6h >> /home/oli/github/nba_cockroach_db/cron.log 2>&1
```

No environment setup needed — `cron.sh` reads `~/.config/sports-hub-credentials.ini` (or
`SPORTS_HUB_CREDENTIALS`). The redirect captures the wrapper's output; the container's own
logs are also available via `docker logs update_tables` until the next run.

Run frequency is otherwise driven from the database: `util.update_schedule.cadence`
selects which run picks up a row, and `util.update_schedule.pause` excludes it from
every run (including a bare `./cron.sh`). The `cadence` column is mirrored in
`sql/tables/util.update_schedule.sql`.

## Notes on the image

- Multi-stage. The build stage needs `build-essential` + `libpq-dev` because sports-hub
  pins `psycopg2`, which publishes no Linux wheels and compiles from source.
- Runtime needs `libpq5` (psycopg2), `tzdata` (`ZoneInfo('Pacific/Auckland')`) and
  `default-jre-headless` — `nbainjuries` starts a JVM via jpype at *import* time and
  `sports_hub.nba` imports it at module top, so Java is needed on every run, not just
  injury runs.
- `uv` is pinned to the version that generated `uv.lock`, and `uv sync --locked` fails the
  build if the lock drifts from `pyproject.toml`. Bump the two together.
- The container runs as root on purpose: a non-root uid could not read the `chmod 600`
  host config through the read-only bind mount, and `/root/.config` is where sports-hub
  resolves it by default.

## Development

```bash
uv sync
uvx ruff check __main__.py
```

`scripts/manual_update.py` is a REPL scratchpad for running individual `hub.*` calls by
hand — not part of the scheduled run, and not in the image. `sql/` holds view, function and
table DDL for reference (hand-applied; the database is the system of record).
