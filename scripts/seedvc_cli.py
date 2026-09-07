"""Run a Seed-VC script with the CPU workarounds applied first.

  python scripts/seedvc_cli.py <script.py> [args...]      (cwd must be vendor/seed-vc)

oneDNN's aarch64 JIT (Xbyak) raises "illegal immediate parameter" on some kernels this model uses,
so the mkldnn backend is disabled and PyTorch's native CPU kernels take over.
"""
import runpy
import sys

import torch

torch.backends.mkldnn.enabled = False
script = sys.argv[1]
sys.argv = [script, *sys.argv[2:]]
runpy.run_path(script, run_name="__main__")
