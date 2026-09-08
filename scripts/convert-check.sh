#!/usr/bin/env bash
# Against the running server: start a conversion of the newest original, prove the API keeps answering while the
# worker runs, and print the result. Non-visual; no UI involved.
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/convert-check.sh
set -uo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source "$HOME/.venvs/voice-lab/bin/activate"
python - <<'EOF'
import time
import httpx

base = "http://127.0.0.1:7860"
lib = httpx.get(f"{base}/api/library", timeout=10).json()
take = next(c for c in lib["clips"] if c["kind"] == "original")
voice = lib["voices"][0]["name"]
print(f"take: {take['label']} ({take['seconds']:.1f} s)  voice: {voice}")
wav = httpx.get(f"{base}{take['url']}", timeout=10).content
t0 = time.time()
job = httpx.post(f"{base}/api/convert", data={"voice": voice, "mode": "v1", "steps": 8, "pitch": 0, "name": "api check", "type": "Voice",
                                              "source": f"original:{take['name']}"}, files={"file": ("take.wav", wav, "audio/wav")}, timeout=30).json()
print(f"job {job['id']} started, estimate {job['estimate']:.0f} s")
slowest = 0.0
while True:
    t = time.time()
    lib_ok = httpx.get(f"{base}/api/library", timeout=10).status_code == 200      # the server must keep answering meanwhile
    slowest = max(slowest, time.time() - t)
    state = httpx.get(f"{base}/api/jobs/{job['id']}", timeout=10).json()
    if state["status"] != "running":
        break
    time.sleep(1)
print(f"status {state['status']} after {time.time() - t0:.0f} s; slowest library call while busy {slowest * 1000:.0f} ms (library ok: {lib_ok})")
if state["status"] == "done":
    c = state["clip"]
    print(f"clip: {c['label']} · {c['type']} · {c.get('voice')} · {c.get('mode')} · {c['seconds']:.2f} s  url {c['url']}")
    exp = httpx.get(f"{base}/api/export/augmented/{c['name']}.opus", timeout=60)
    print(f"export: {exp.status_code} {len(exp.content)} bytes")
else:
    print("error:", state["error"])
EOF
