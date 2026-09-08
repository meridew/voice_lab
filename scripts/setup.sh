#!/usr/bin/env bash
# One-time environment setup on the WSL2 side. No sudo needed: uv brings its own Python.
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/setup.sh
set -euo pipefail
PROJECT=/mnt/c/Users/danie/vscode-workspace/voice-lab
VENV="$HOME/.venvs/voice-lab"
export PATH="$HOME/.local/bin:$PATH"

echo "== uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
uv --version

echo "== python 3.10 venv at $VENV"
uv python install 3.10
if [ ! -x "$VENV/bin/python" ]; then
  uv venv "$VENV" --python 3.10
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python --version

echo "== torch (CPU wheels for aarch64)"
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

echo "== seed-vc source, pinned"
SEEDVC_COMMIT=51383efd921027683c89e5348211d93ff12ac2a8
mkdir -p "$PROJECT/vendor"
if [ ! -d "$PROJECT/vendor/seed-vc/.git" ]; then
  git clone https://github.com/Plachtaa/seed-vc "$PROJECT/vendor/seed-vc"
fi
git -C "$PROJECT/vendor/seed-vc" checkout -q "$SEEDVC_COMMIT" -- .
git -C "$PROJECT/vendor/seed-vc" checkout -q "$SEEDVC_COMMIT"
# Local patches (see patches/seed-vc.patch): oneDNN's aarch64 JIT rejects BigVGAN's depthwise anti-aliasing conv1d
# ("illegal immediate parameter"), so that one op bypasses oneDNN; and v2's autoregressive generate takes a token
# budget so a runaway stops after seconds instead of 4000 tokens.
git -C "$PROJECT/vendor/seed-vc" apply "$PROJECT/patches/seed-vc.patch"

echo "== seed-vc runtime deps + app deps, resolved together so the pins hold"
# Seed-VC pins minus CUDA nightlies, GUI and evaluation extras. soundfile 0.12.1 has no bundled libsndfile
# for aarch64 Linux, 0.13 does and is API-compatible. FastAPI serves the page and the API.
uv pip install \
  accelerate "scipy==1.13.1" "librosa==0.10.2" "huggingface-hub>=0.28.1" "munch==4.0.0" "einops==0.8.0" \
  "descript-audio-codec==1.0.0" "pydub==0.25.1" "transformers==4.46.3" \
  "numpy==1.26.4" "hydra-core==1.3.2" pyyaml python-dotenv "soundfile>=0.13.1" \
  kokoro pedalboard \
  noisereduce pyloudnorm soxr fastapi uvicorn python-multipart
uv pip install imageio-ffmpeg || echo "(imageio-ffmpeg unavailable; mp3/webm imports will need ffmpeg)"
echo "== dev tools (the checks in scripts/)"
uv pip install ruff httpx

echo "== sanity"
python - <<'EOF'
import torch, torchaudio, numpy, librosa, fastapi, pedalboard, kokoro
print("torch", torch.__version__, "threads", torch.get_num_threads(), "cuda", torch.cuda.is_available())
print("numpy", numpy.__version__, "librosa", librosa.__version__, "fastapi", fastapi.__version__, "pedalboard", pedalboard.__version__)
EOF
echo "== done: $VENV"
