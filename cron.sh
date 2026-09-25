#!/bin/bash
# Usage: ./cron.sh                 -> all unpaused tables in util.update_schedule
#        ./cron.sh tbl_a,tbl_b     -> only those table_names
#
# Secrets live outside the repo, in $CONFIG_DIR (chmod 700 dir, chmod 600 files):
#   $CONFIG_DIR/credentials.ini    sports-hub DB / platform credentials
#   $CONFIG_DIR/.env               DB_CON, SMTP_USER, SMTP_PASSWORD (see env.example)

export PATH=/usr/local/bin:/usr/bin:/bin

IMAGE_NAME='shaggycamel/nba_cockroach_db:latest'
CONTAINER_NAME='update_tables'
CONFIG_DIR="${NBA_CONFIG_DIR:-$HOME/.config/nba_cockroach_db}"

if ! docker info >/dev/null 2>&1; then
    echo 'Docker daemon not responding. Ensure it is enabled to start on boot.'
    exit 1
fi

for f in credentials.ini .env; do
    if [ ! -f "$CONFIG_DIR/$f" ]; then
        echo "Missing $CONFIG_DIR/$f"
        exit 1
    fi
done

docker pull -q "$IMAGE_NAME" >/dev/null 2>&1 || echo 'docker pull failed; using local image'

# Container is kept after the run (no --rm) so `docker logs` works until the next run.
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1
docker run --name "$CONTAINER_NAME" \
    --env-file "$CONFIG_DIR/.env" \
    -v "$CONFIG_DIR/credentials.ini:/app/credentials.ini:ro" \
    "$IMAGE_NAME" "$@"
status=$?

echo '------------------------------------------'
echo "Container '$CONTAINER_NAME' exited with status $status."
echo "Check logs with: docker logs $CONTAINER_NAME"
echo '------------------------------------------'
exit $status