#!/bin/bash

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[INFO] Limpando instâncias antigas do Mininet..."
sudo mn -c

echo "[INFO] Iniciando topologia Mininet..."
echo "[INFO] Certifique-se de que o controlador POX já está rodando em outro terminal."
echo ""

cd "$PROJECT_DIR"
sudo python3 topology/topo_dash.py