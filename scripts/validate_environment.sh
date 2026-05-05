#!/bin/bash

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
POX_DIR="$PROJECT_DIR/tools/pox"

echo "[INFO] Validando ambiente..."

command -v git >/dev/null && echo "[OK] git instalado"
command -v mn >/dev/null && echo "[OK] Mininet instalado"
command -v ovs-vsctl >/dev/null && echo "[OK] Open vSwitch instalado"
command -v python3 >/dev/null && echo "[OK] Python 3 instalado"
command -v ffmpeg >/dev/null && echo "[OK] FFmpeg instalado"
command -v vlc >/dev/null && echo "[OK] VLC instalado"
command -v iperf >/dev/null && echo "[OK] iperf instalado"
command -v iperf3 >/dev/null && echo "[OK] iperf3 instalado"
command -v tcpdump >/dev/null && echo "[OK] tcpdump instalado"
command -v make >/dev/null && echo "[OK] make instalado"

if [ -f "$POX_DIR/pox.py" ]; then
    echo "[OK] Controlador POX encontrado em tools/pox"
else
    echo "[ERRO] Controlador POX não encontrado."
    echo "Execute: make install"
    exit 1
fi

echo "[OK] Ambiente validado com sucesso."
