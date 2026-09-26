#!/bin/bash
# Usage: ./cron.sh                 -> all unpaused tables in util.update_schedule
#        ./cron.sh tbl_a,tbl_b     -> only those table_names
#
# All configuration lives in credentials.ini (chmod 600) next to this script, in the repo
# root: DB / platform credentials, [runtime] db_con, [smtp] alerts. See
# credentials.ini.example. It is bind-mounted read-only at /app/credentials.ini, which is
# where sports-hub and __main__.py both read it from.
#
# Resolved from the script's own location, not the caller's cwd, so cron needs no setup.

export PATH=/usr/local/bin:/usr/bin:/bin

# Built locally on this host (see README) -- no registry, so no pull.
IMAGE_NAME='nba_cockroach_db:latest'
CONTAINER_NAME='update_tables'
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/credentials.ini"

if ! docker info >/dev/null 2>&1; then
    echo 'Docker daemon not responding. Ensure it is enabled to start on boot.'
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Missing $CONFIG_FILE"
    echo "Copy $SCRIPT_DIR/credentials.ini.example to it and fill it in."
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
    -v "$CONFIG_FILE:/app/credentials.ini:ro" \
    "$IMAGE_NAME" "$@"
status=$?

echo '------------------------------------------'
echo "Container '$CONTAINER_NAME' exited with status $status."
echo "Check logs with: docker logs $CONTAINER_NAME"
echo '------------------------------------------'
exit $status