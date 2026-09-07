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

echo "== seed-vc source"
mkdir -p "$PROJECT/vendor"
if [ ! -d "$PROJECT/vendor/seed-vc/.git" ]; then
  git clone --depth 1 https://github.com/Plachtaa/seed-vc "$PROJECT/vendor/seed-vc"
fi
# Local patch: inference_v2.py hard-codes float16, which is unreliable on the CPU.
sed -i 's/^dtype = torch.float16$/dtype = torch.float16 if device.type != "cpu" else torch.float32  # voice-lab: fp16 is unreliable on CPU/' "$PROJECT/vendor/seed-vc/inference_v2.py"

echo "== seed-vc runtime deps + app deps, resolved together so the pins hold"
# Seed-VC pins minus CUDA nightlies, GUI and evaluation extras. soundfile 0.12.1 has no bundled libsndfile
# for aarch64 Linux, 0.13 does and is API-compatible. Gradio 5 is the API this UI is written against.
uv pip install \
  accelerate "scipy==1.13.1" "librosa==0.10.2" "huggingface-hub>=0.28.1" "munch==4.0.0" "einops==0.8.0" \
  "descript-audio-codec==1.0.0" "pydub==0.25.1" "transformers==4.46.3" \
  "numpy==1.26.4" "hydra-core==1.3.2" pyyaml python-dotenv "soundfile>=0.13.1" \
  kokoro pedalboard "gradio>=5.0,<6"
uv pip install imageio-ffmpeg || echo "(imageio-ffmpeg unavailable; mp3/webm imports will need ffmpeg)"

echo "== sanity"
python - <<'EOF'
import torch, torchaudio, numpy, librosa, gradio, pedalboard, kokoro
print("torch", torch.__version__, "threads", torch.get_num_threads(), "cuda", torch.cuda.is_available())
print("numpy", numpy.__version__, "librosa", librosa.__version__, "gradio", gradio.__version__, "pedalboard", pedalboard.__version__)
EOF
echo "== done: $VENV"
