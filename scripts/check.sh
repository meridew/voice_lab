#!/usr/bin/env bash
# The verification kernel, no models and no UI: lint, then the API in-process (library, both pages, an audio file, an export, a rename).
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/check.sh
set -uo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source "$HOME/.venvs/voice-lab/bin/activate"
echo "== ruff" && ruff check app scripts
echo "== api"
PYTHONPATH=app python - <<'EOF' 2>&1 | grep -vE "Warning|warn\(|warnings.warn"
from fastapi.testclient import TestClient
import server

client = TestClient(server.app)
lib = client.get("/api/library").json()
print("voices:", [v["name"] for v in lib["voices"]])
print("clips:", len(lib["clips"]), "e.g.", {k: v for k, v in lib["clips"][0].items() if k in ("kind", "type", "label", "when", "seconds", "url")} if lib["clips"] else None)
page = client.get("/")
print("page:", page.status_code, "bytes", len(page.content), "index" if b"Voice Lab" in page.content else "unexpected")
first = lib["clips"][0]
audio = client.get(first["url"])
print("audio:", audio.status_code, audio.headers.get("content-type"), len(audio.content), "bytes")
exp = client.get(f"/api/export/{first['kind']}/{first['name']}.opus")
print("export:", exp.status_code, exp.headers.get("content-disposition"), len(exp.content), "bytes")
lp = client.get("/library.html")
print("library page:", lp.status_code, "ok" if b"library.js" in lp.content else "unexpected")
upd = client.patch(f"/api/clips/{first['kind']}/{first['name']}", data={"label": first["label"], "type": first["type"]})
print("update:", upd.status_code, upd.json().get("label"), upd.json().get("type"))
EOF
