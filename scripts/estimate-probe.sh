#!/usr/bin/env bash
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC1091
source "$HOME/.venvs/voice-lab/bin/activate"
cd /mnt/c/Users/danie/vscode-workspace/voice-lab
python - <<'EOF'
from gradio_client import Client
c = Client("http://127.0.0.1:7860", verbose=False)
names = sorted(c.view_api(all_endpoints=True, return_format="dict", print_info=False)["named_endpoints"])
print([n for n in names if "estimate" in n])
print(c.predict("20260907-114706_male-stand-in.wav", 15, "v1", api_name="/_estimate"))
EOF
