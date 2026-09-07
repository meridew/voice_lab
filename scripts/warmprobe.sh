#!/usr/bin/env bash
# Time a cold and a warm conversion through the running UI (server started with VOICE_LAB_SHOW_API=1).
set -uo pipefail
PROJECT=/mnt/c/Users/danie/vscode-workspace/voice-lab
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC1091
source "$HOME/.venvs/voice-lab/bin/activate"
cd "$PROJECT"
PYTHONPATH="$PROJECT/app" python scripts/warmprobe.py
