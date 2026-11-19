#!/usr/bin/env bash
# Run from a trusted host with PGDATABASE, PGUSER, PGPASSWORD and PGHOST set.
set -euo pipefail
umask 077
: "${PGDATABASE:?Set PGDATABASE}" "${PGHOST:?Set PGHOST}"
destination=${1:?Supply a private backup directory}
mkdir -p -- "$destination"
stage=$(mktemp -d "$destination/.devpulse-XXXXXXXX")
trap 'rm -f -- "$stage/archive"; rmdir -- "$stage"' EXIT
pg_dump --format=custom --no-owner --no-acl --file="$stage/archive"
pg_restore --list "$stage/archive" >/dev/null
name="devpulse-$(date -u +%Y%m%dT%H%M%SZ)-${stage##*-}.dump"
mv -- "$stage/archive" "$destination/$name"
printf '%s\n' "$destination/$name"
