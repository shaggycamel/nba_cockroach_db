#!/bin/bash

IMAGE_NAME='shaggycamel/nba_cockroach_db:latest' 
CONTAINER_NAME='update_tables'

if ! docker info >/dev/null 2>&1; then
    echo 'Docker daemon not responding. Ensure it is enabled to start on boot.'
    exit 1
fi

docker stop $CONTAINER_NAME >/dev/null 2>&1
docker rm $CONTAINER_NAME >/dev/null 2>&1
docker run --name $CONTAINER_NAME $IMAGE_NAME "$@"

echo '------------------------------------------'
echo "Container '$CONTAINER_NAME' is running."
echo 'Check logs with: docker logs '$CONTAINER_NAME''
echo '------------------------------------------'
