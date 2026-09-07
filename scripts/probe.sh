#!/usr/bin/env bash
# Environment probe for the WSL2 side. Run: wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/probe.sh
echo "arch: $(uname -m)"
echo "kernel: $(uname -r)"
echo "distro: $(. /etc/os-release && echo "$PRETTY_NAME")"
echo "python3: $(python3 --version 2>&1)"
if sudo -n true 2>/dev/null; then echo "sudo: passwordless"; else echo "sudo: needs password"; fi
echo "uv: $(command -v uv || echo none) $(command -v uv >/dev/null && uv --version)"
echo "git: $(git --version 2>&1)"
echo "nproc: $(nproc)"
echo "mem: $(free -g | awk '/Mem/{print $2 " GB total, " $7 " GB available"}')"
echo "home free: $(df -h ~ | tail -1 | awk '{print $4}')"
echo "espeak-ng: $(command -v espeak-ng || echo none)"
echo "ffmpeg: $(command -v ffmpeg || echo none)"
echo "curl: $(command -v curl || echo none)"
echo "windows fs mount: $(ls -d /mnt/c/Users/danie/vscode-workspace/voice-lab 2>/dev/null || echo missing)"
echo "localhost forwarding: $(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null)"
echo "hf cache: $(du -sh ~/.cache/huggingface 2>/dev/null | cut -f1 || echo none)"
