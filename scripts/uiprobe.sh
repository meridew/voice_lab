#!/usr/bin/env bash
# Wait for the UI server, then exercise its endpoints through the Gradio client (needs VOICE_LAB_SHOW_API=1 on the server).
set -uo pipefail
PROJECT=/mnt/c/Users/danie/vscode-workspace/voice-lab
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC1091
source "$HOME/.venvs/voice-lab/bin/activate"
cd "$PROJECT"
for _ in $(seq 1 30); do
  if curl -s -o /dev/null http://127.0.0.1:7860/; then break; fi
  sleep 3
done
PYTHONPATH="$PROJECT/app" python scripts/uiprobe.py 2>&1 | tail -15
echo "--- server chain log ---"
grep -E '\[chain\]|Traceback|Error' "${1:-logs/app3.log}" | tail -8
