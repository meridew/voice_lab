#!/usr/bin/env bash
# Headless end-to-end check inside WSL2 (downloads Seed-VC checkpoints on first run).
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/smoke.sh [--steps 10] [--v2]
set -euo pipefail
PROJECT=/mnt/c/Users/danie/vscode-workspace/voice-lab
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC1091
source "$HOME/.venvs/voice-lab/bin/activate"
cd "$PROJECT"
export PYTHONPATH="$PROJECT/app"
export HF_HUB_DISABLE_TELEMETRY=1
python scripts/smoke.py "$@"
