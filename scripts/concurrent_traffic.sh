#!/bin/bash
#
# Gera tráfego concorrente com iperf para induzir congestionamento.
# Executar DENTRO do namespace de um host cliente, a partir do CLI do Mininet.
#
# Primeiro garanta um servidor iperf no h1:
#   mininet> h1 iperf -s -p 5001 &
#
# Depois gere carga a partir de outros clientes (em paralelo):
#   mininet> h3 bash scripts/concurrent_traffic.sh 10.0.0.1 60 &
#   mininet> h4 bash scripts/concurrent_traffic.sh 10.0.0.1 60 &
#
# Uso: concurrent_traffic.sh <ip_servidor> [duracao_s] [porta]

SERVER="${1:-10.0.0.1}"
DURATION="${2:-60}"
PORT="${3:-5001}"

echo "[INFO] Gerando tráfego concorrente: -> $SERVER:$PORT por ${DURATION}s"
iperf -c "$SERVER" -p "$PORT" -t "$DURATION"
