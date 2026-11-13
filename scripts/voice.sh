#!/usr/bin/env bash
# Runs the voice program natively instead of as the compose stack's `voice` service: an option for Mac developers
# (Docker on a Mac runs it in a VM). Point the api at it with SPEECH_URL=http://host.docker.internal:8791.
# Everyone else: `docker compose --profile voice up -d`, or Settings → Voice in the desktop app.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "First run downloads about 115 MB of Kokoro voice files and about 460 MB for Whisper small (needs ~3 GB free disk)."
exec uv run --project voice python voice/server.py
