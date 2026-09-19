#!/bin/sh
# Set the timezone so cron fires on America/New_York wall-clock time, then hand
# off to busybox crond in the foreground (PID 1) so logs reach `docker logs`.
set -eu

: "${TZ:=America/New_York}"
if [ -f "/usr/share/zoneinfo/$TZ" ]; then
  cp "/usr/share/zoneinfo/$TZ" /etc/localtime
  echo "$TZ" > /etc/timezone
fi
export TZ

echo "[entrypoint] Contract Scout scheduler starting"
echo "[entrypoint] TZ=$TZ  now=$(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "[entrypoint] API base: ${SCRAPE_API_BASE:-http://backend:8000/api/v1}"
echo "[entrypoint] Schedule: every 30 min, 7:00am-10:00pm, Mon-Sat"

# Optional immediate pass on boot (handy for verifying config).
if [ "${RUN_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] RUN_ON_START=true — running one pass now"
  /app/scrape.sh || true
fi

exec crond -f -l 8 -L /dev/stdout
