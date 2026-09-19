#!/bin/sh
# R10: the real docker (REAL_DOCKER), except that pg_dump fails, as a backup that can't be written would.
case "$*" in
  *pg_dump*) echo 'pg_dump: error: forced by the test' >&2; exit 1 ;;
esac
exec "$REAL_DOCKER" "$@"
