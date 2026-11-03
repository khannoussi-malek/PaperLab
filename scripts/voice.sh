#!/usr/bin/env bash
# Starts PaperLab's optional voice program on 127.0.0.1:8791.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "First run downloads about 115 MB of Kokoro voice files and about 460 MB for Whisper small (needs ~3 GB free disk)."
exec uv run --project voice python voice/server.py
