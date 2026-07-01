#!/bin/bash
#
# Inicia o controlador SDN da Etapa 3 (ext.qoe_guard): encaminhamento L2 +
# deteccao de congestionamento + priorizacao dinamica do trafego DASH.
#
# Variaveis de ambiente opcionais:
#   MITIGATE   True/False  (padrao True)  — habilita a mitigacao
#   CAPACITY   Mbps        (padrao 10)    — capacidade do enlace gargalo
#   BOTTLENECK intf        (padrao s1-eth2)
#   PORT       num         (padrao 2)     — porta de saida gargalo em s1

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
POX_DIR="$PROJECT_DIR/tools/pox"

MITIGATE="${MITIGATE:-True}"
CAPACITY="${CAPACITY:-10}"
BOTTLENECK="${BOTTLENECK:-s1-eth2}"
PORT="${PORT:-2}"

if [ ! -f "$POX_DIR/pox.py" ]; then
    echo "[ERRO] POX nao encontrado em: $POX_DIR"
    echo "Execute primeiro: make install"
    exit 1
fi

# A arvore tools/pox e baixada pelo install.sh (e ignorada no git); o nosso
# app fica versionado em controller/ e e copiado para ext/ antes de subir.
mkdir -p "$POX_DIR/ext"
cp "$PROJECT_DIR/controller/qoe_guard.py" "$POX_DIR/ext/qoe_guard.py"

echo "[INFO] Iniciando controlador SDN POX (Etapa 3)..."
echo "[INFO] Aplicacao: ext.qoe_guard (mitigate=$MITIGATE, gargalo=$BOTTLENECK @ ${CAPACITY} Mbps)"
echo "[INFO] Porta padrao OpenFlow: 6633"
echo "[INFO] Decisoes registradas em: results/etapa3/decisions.log"
echo "[INFO] Deixe este terminal aberto."
echo ""

cd "$POX_DIR"
PYTHONPATH="$POX_DIR/ext:$PROJECT_DIR:${PYTHONPATH:-}" python3 pox.py qoe_guard \
    --mitigate="$MITIGATE" \
    --capacity="$CAPACITY" \
    --bottleneck="$BOTTLENECK" \
    --port="$PORT"
