#!/usr/bin/env bash
# Launch the Voice Lab server (FastAPI + the single-page app) from WSL2. Open http://localhost:7860 in a Windows browser.
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/run.sh
set -euo pipefail
PROJECT=/mnt/c/Users/danie/vscode-workspace/voice-lab
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC1091
source "$HOME/.venvs/voice-lab/bin/activate"
cd "$PROJECT"
export PYTHONPATH="$PROJECT/app"
export HF_HUB_DISABLE_TELEMETRY=1
exec python app/server.py "$@"
