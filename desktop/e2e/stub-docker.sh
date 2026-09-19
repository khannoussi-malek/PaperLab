#!/bin/sh
# A docker for the desktop app's E2E: it answers from STUB_* variables and appends every call to STUB_LOG.
#   STUB_INFO=down            docker info fails as when the daemon isn't running
#   STUB_COMPOSE_VERSION=2.23.3
#   STUB_UP_ERROR=<line>      compose up fails with this line
#   STUB_STOP_SECONDS=2       compose stop takes this long, then logs "stopped"
printf '%s\n' "$*" >> "${STUB_LOG:-/dev/null}"
case "$1" in
  info)
    if [ "${STUB_INFO:-ok}" = ok ]; then echo linux; exit 0; fi
    echo 'Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?' >&2
    exit 1 ;;
  image) exit 0 ;; # this version's image is here: nothing to pull
esac
case "$*" in
  *'version --short'*) echo "${STUB_COMPOSE_VERSION:-2.29.1}" ;;
  *' up -d'*) if [ -n "${STUB_UP_ERROR:-}" ]; then echo "$STUB_UP_ERROR" >&2; exit 1; fi ;;
  *' stop'*) sleep "${STUB_STOP_SECONDS:-0}"; echo stopped >> "${STUB_LOG:-/dev/null}" ;;
esac
exit 0
