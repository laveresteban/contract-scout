#!/bin/sh
# One scrape pass: pull the user's saved searches from the Contract Scout UI
# and re-scrape each one, picking up newly posted jobs.
#
# Source of truth is the UI's saved searches (GET /prefs/saved-searches). Each
# row's `filters` object holds the exact query + options the user chose in the
# search form, so we POST that straight to /search — the same call the UI's
# "Search" button makes. Nothing is hard-coded here: add/edit searches in the
# app and the next pass uses them.
#
# Only server-backed (signed-in) saved searches are reachable headlessly, so a
# bearer token is required. Searches kept only in a browser's localStorage
# (unauthenticated) can't be seen from here.
#
# Env:
#   SCRAPE_API_BASE   base URL incl. /api/v1 (default http://backend:8000/api/v1)
#   SCRAPE_AUTH_TOKEN bearer token for the account whose saved searches to run (required)
#   SCRAPE_TIMEOUT    per-request timeout seconds (default 60)
#   ONLY_ALERTS       "true" = only run saved searches with alerts enabled (default false)
set -eu

API_BASE="${SCRAPE_API_BASE:-http://backend:8000/api/v1}"
TOKEN="${SCRAPE_AUTH_TOKEN:-}"
TIMEOUT="${SCRAPE_TIMEOUT:-60}"
ONLY_ALERTS="${ONLY_ALERTS:-false}"
SEARCHES="$(mktemp)"
RESP="$(mktemp)"

ts() { date '+%Y-%m-%d %H:%M:%S %Z'; }
log() { echo "[$(ts)] $*"; }
cleanup() { rm -f "$SEARCHES" "$RESP"; }
trap cleanup EXIT

if [ -z "$TOKEN" ]; then
  log "ERROR SCRAPE_AUTH_TOKEN is not set — cannot read your saved searches. Set it to a signed-in account token."
  exit 1
fi

# --- 1. Fetch the saved searches configured in the UI ----------------------
set +e
code=$(curl -sS -o "$SEARCHES" -w '%{http_code}' --max-time "$TIMEOUT" \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/prefs/saved-searches"); rc=$?
set -e

if [ "$rc" -ne 0 ]; then
  log "FAIL could not reach $API_BASE/prefs/saved-searches (curl rc=$rc) — inconclusive, retrying next pass"
  exit 0
fi
if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
  log "ERROR GET /prefs/saved-searches returned HTTP $code"
  [ "$code" = "401" ] && log "      (401 — the token is missing/expired)"
  exit 1
fi
if ! jq -e 'type=="array"' "$SEARCHES" >/dev/null 2>&1; then
  log "ERROR unexpected response from /prefs/saved-searches (not a JSON array)"
  exit 1
fi

if [ "$ONLY_ALERTS" = "true" ]; then
  jq '[.[] | select(.alert_enabled == true)]' "$SEARCHES" > "$SEARCHES.f" && mv "$SEARCHES.f" "$SEARCHES"
fi

count=$(jq 'length' "$SEARCHES")
log "Scrape pass start — $count saved search(es)$( [ "$ONLY_ALERTS" = "true" ] && echo ' with alerts enabled') -> $API_BASE/search"
if [ "$count" -eq 0 ]; then
  log "Nothing to do — save a search in the Contract Scout UI first."
  exit 0
fi

# --- 2. Re-scrape each saved search ----------------------------------------
post() {
  # $1 = filters JSON body
  printf '%s' "$1" | curl -sS -o "$RESP" -w '%{http_code}' --max-time "$TIMEOUT" \
    -X POST "$API_BASE/search" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    --data-binary @-
}

i=0
ok=0; warn=0; fail=0
while [ "$i" -lt "$count" ]; do
  name=$(jq -r ".[$i].name // \"search-$i\"" "$SEARCHES")
  # `filters` (server) is the params object; fall back to `params` just in case.
  body=$(jq -c ".[$i].filters // .[$i].params // {}" "$SEARCHES")

  set +e
  code=$(post "$body"); rc=$?
  set -e

  if [ "$rc" -ne 0 ]; then
    # Network/timeout: inconclusive, never fatal — matches the app's
    # "transient failure is not a dead job" rule. Retried next pass.
    log "FAIL  [$name] curl rc=$rc (network/timeout) — inconclusive, retrying next pass"
    fail=$((fail+1))
  elif [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
    n=$(jq 'if type=="array" then length elif type=="object" and has("jobs") then (.jobs|length) elif type=="object" and has("count") then .count else "?" end' "$RESP" 2>/dev/null || echo "?")
    log "OK    [$name] HTTP $code — $n job(s)"
    ok=$((ok+1))
  else
    log "WARN  [$name] HTTP $code"
    warn=$((warn+1))
  fi
  i=$((i+1))
done

log "Scrape pass done — ok=$ok warn=$warn fail=$fail"
