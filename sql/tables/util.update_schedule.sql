-- util.update_schedule drives __main__.py. Each row is one table update, and its
-- `cadence` names the cron.sh argument that runs it: `./cron.sh daily` selects every
-- unpaused row with cadence = 'daily', while a bare `./cron.sh` runs every unpaused row
-- regardless of cadence.
--
-- Hand-applied, like sql/views and sql/functions: the database is the system of record
-- and this file is the mirror.
--
-- TEXT, not STRING: STRING is a Cockroach alias with no Postgres equivalent, and this
-- DDL is applied to both. Nullable so it can be added before the backfill; tighten to
-- NOT NULL once every row has a cadence.

ALTER TABLE util.update_schedule ADD COLUMN IF NOT EXISTS cadence TEXT;

-- Assign per object, e.g.:
-- UPDATE util.update_schedule SET cadence = 'daily';
-- UPDATE util.update_schedule SET cadence = 'intraday' WHERE table_name = 'nba_injuries';

-- Optional, once no row is left unassigned:
-- ALTER TABLE util.update_schedule ALTER COLUMN cadence SET NOT NULL;
