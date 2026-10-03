#!/bin/bash
# Usage: ./cron.sh                 -> all unpaused tables in util.update_schedule
#        ./cron.sh tbl_a,tbl_b     -> only those table_names
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