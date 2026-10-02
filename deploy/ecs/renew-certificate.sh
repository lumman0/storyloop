#!/bin/sh
set -eu

data_dir=${STORY_DATA_DIR:-/srv/storyloop-data}
compose_dir=${STORY_COMPOSE_DIR:-/opt/storyloop/deploy/ecs}

docker run --rm \
  -v "$data_dir/acme-challenge:/var/www/acme" \
  -v "$data_dir/letsencrypt:/etc/letsencrypt" \
  certbot/certbot:latest renew --quiet --no-random-sleep-on-renew

cd "$compose_dir"
docker compose exec -T web nginx -s reload
