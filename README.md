# nba_cockroach_db

Scheduled table updates for the NBA / fantasy database.

`__main__.py` reads `util.update_schedule`, calls each row's `associated_function` on a
[sports-hub](https://github.com/shaggycamel/sports-hub) `SportsHub`, writes one row per
table to `util.update_log`, emails any failures, and exits non-zero if anything failed.

```
python __main__.py                 # every table where pause IS FALSE
python __main__.py tbl_a,tbl_b     # only these table_names (alternate-frequency runs)
```

It runs as a Docker container, once per cron job, on a single always-on host (the NUC).

## Configuration

Everything lives in one file, `credentials.ini`, read from the working directory — the
same file sports-hub reads for its DB and platform credentials. Copy
[credentials.ini.example](credentials.ini.example) and fill it in. Never commit it.

| Section    | Key        | Env override    | Purpose                                     |
| ---------- | ---------- | --------------- | ------------------------------------------- |
| `[runtime]`| `db_con`   | `DB_CON`        | which DB section to write to                |
| `[smtp]`   | `user`     | `SMTP_USER`     | Gmail address failure alerts are sent from  |
| `[smtp]`   | `password` | `SMTP_PASSWORD` | Gmail app password                          |
| `[smtp]`   | `to`       | `ALERT_TO`      | recipient; defaults to `user`               |

Environment variables win when set, so `os.environ['DB_CON'] = 'postgres'` still works in
an interactive console. Without `[smtp] user` + `password` the failure email is skipped
and the run simply exits 1.

The repo's own `credentials.ini` should point at `[runtime] db_con = postgres` so a stray
local run cannot write to cockroach.

## Deploying to the NUC

The image is built on the NUC itself — native amd64, no registry, and no credentials ever
leave the box.

```bash
# 1. one-off: the config directory, outside the repo
mkdir -p ~/.config/nba_cockroach_db && chmod 700 ~/.config/nba_cockroach_db
cp credentials.ini.example ~/.config/nba_cockroach_db/credentials.ini
chmod 600 ~/.config/nba_cockroach_db/credentials.ini
$EDITOR ~/.config/nba_cockroach_db/credentials.ini   # real creds, db_con = cockroach

# 2. build (repeat after every git pull)
cd ~/git/nba_cockroach_db && git pull
docker build -t nba_cockroach_db:latest .

# 3. run
./cron.sh                  # all unpaused tables
./cron.sh nba_teams        # just one
```

`cron.sh` bind-mounts `credentials.ini` read-only at `/app/credentials.ini`, so nothing
secret is in the image. It keeps the container after the run (no `--rm`) so
`docker logs update_tables` works until the next run, and it propagates the exit status.

Crontab — cron has no `PATH`, which is why `cron.sh` sets one:

```cron
0  3 * * *  /home/<user>/git/nba_cockroach_db/cron.sh
0 */6 * * * /home/<user>/git/nba_cockroach_db/cron.sh nba_injuries
```

Run frequency is otherwise driven from the database: `util.update_schedule.pause`
controls what a bare `./cron.sh` picks up.

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
  host `credentials.ini` through the read-only bind mount.

## Development

```bash
uv sync
uvx ruff check __main__.py
```

`scripts/manual_update.py` is a REPL scratchpad for running individual `hub.*` calls by
hand — not part of the scheduled run, and not in the image. `sql/` holds view and function
DDL for reference.
