#!/bin/sh
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
if [ "$#" -ne 2 ]; then
    printf 'Usage: sh deploy/deploy.sh RUN SITE_HOST\nRun on the approved VM after copying .env and the demo bundle.\n' >&2
    exit 2
fi
export LORE_RESULTS_RUN="$1" SITE_HOST="$2" HYDRA_ADVERTISED=hydradb:7687
test -f .env || { printf 'Copy the private .env first; do not put it in Git.\n' >&2; exit 1; }
test -f "results/$LORE_RESULTS_RUN/demo.json" || { printf 'Measured demo selection is missing.\n' >&2; exit 1; }
test -f data/bird/paths.json || { printf 'Install the demo data bundle first.\n' >&2; exit 1; }
docker info >/dev/null 2>&1 || {
    printf 'Docker is unavailable. Ask the owner to install/configure it; this script never runs sudo.\n' >&2
    exit 1
}
docker compose --profile prod config --quiet
docker compose --profile prod up -d --build --wait --wait-timeout 240
printf 'Deployment started at https://%s\nVerify health and a full sandbox round from another network.\n' "$SITE_HOST"
