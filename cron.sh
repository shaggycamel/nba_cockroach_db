#!/bin/bash
# Usage: ./cron.sh                      -> all unpaused tables in util.update_schedule
#        ./cron.sh daily,intraday             -> only rows whose cadence is one of these
#        ./cron.sh daily intraday             -> same; space- or comma-separated
#
# All configuration lives in the system-wide sports-hub credentials file
# (~/.config/sports-hub-credentials.ini, chmod 600), or SPORTS_HUB_CREDENTIALS if set:
# DB / platform credentials, [runtime] db_con, [smtp] alerts. It is bind-mounted read-only
# at /root/.config/sports-hub-credentials.ini, which is where sports-hub and __main__.py
# both read it from (the container runs as root, so that is Path.home()).
#
# Resolved independently of the caller's cwd, so cron needs no setup.

export PATH=/usr/local/bin:/usr/bin:/bin

# Built locally on this host (see README) -- no registry, so no pull.
IMAGE_NAME='nba_cockroach_db:latest'
CONTAINER_NAME='update_tables'
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${SPORTS_HUB_CREDENTIALS:-$HOME/.config/sports-hub-credentials.ini}"

# Serialise runs. Cron ticks can overlap when a run is slow, and the `docker rm -f`
# below would then kill the in-flight container mid-write. Wait up to an hour for the
# lock (so a normal overrun simply queues), then give up rather than pile up more.
LOCK_FILE="${LOCK_FILE:-${TMPDIR:-/tmp}/nba_cockroach_db.lock}"
exec 9>"$LOCK_FILE"
if ! flock -w 3600 9; then
    echo 'Another run is still in progress after 1h; skipping this tick.'
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo 'Docker daemon not responding. Ensure it is enabled to start on boot.'
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Missing $CONFIG_FILE"
    echo "Create it (chmod 600) with the DB/platform, [runtime] and [smtp] sections."
    exit 1
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "Image '$IMAGE_NAME' not found. Build it first:"
    echo "  cd $SCRIPT_DIR && git pull && docker build -t $IMAGE_NAME ."
    exit 1
fi

# Container is kept after the run (no --rm) so `docker logs` works until the next run.
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1
docker run --name "$CONTAINER_NAME" \
    -v "$CONFIG_FILE:/root/.config/sports-hub-credentials.ini:ro" \
    "$IMAGE_NAME" "$@"
status=$?

echo '------------------------------------------'
echo "Container '$CONTAINER_NAME' exited with status $status."
echo "Check logs with: docker logs $CONTAINER_NAME"
echo '------------------------------------------'
exit $status