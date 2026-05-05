#!/bin/bash

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
POX_DIR="$PROJECT_DIR/tools/pox"

if [ ! -f "$POX_DIR/pox.py" ]; then
    echo "[ERRO] POX não encontrado em:"
    echo "  $POX_DIR"
    echo "Execute primeiro:"
    echo "  make install"
    exit 1
fi

echo "[INFO] Iniciando controlador SDN POX..."
echo "[INFO] Aplicação: forwarding.l2_learning"
echo "[INFO] Porta padrão OpenFlow: 6633"
echo "[INFO] Deixe este terminal aberto."
echo ""

cd "$POX_DIR"
python3 pox.py forwarding.l2_learning
