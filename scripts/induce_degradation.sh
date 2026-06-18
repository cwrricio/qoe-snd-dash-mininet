#!/bin/bash
#
# Induz degradação de rede em uma interface usando tc (netem/tbf).
# Deve ser executado DENTRO do namespace do host, a partir do CLI do Mininet:
#
#   mininet> h1 bash scripts/induce_degradation.sh h1-eth0 --bw 3 --delay 100ms --loss 2
#
# Para limpar:
#
#   mininet> h1 bash scripts/induce_degradation.sh h1-eth0 --clear
#
# Parâmetros (todos opcionais, combináveis):
#   --bw <Mbps>      limita a banda (tbf)
#   --delay <tc>     atraso, ex.: 100ms
#   --jitter <tc>    variação do atraso, ex.: 20ms (requer --delay)
#   --loss <pct>     perda de pacotes em %, ex.: 5
#   --clear          remove toda a degradação da interface

set -e

IFACE="${1:-}"
if [ -z "$IFACE" ]; then
    echo "[ERRO] Informe a interface. Ex.: h1-eth0"
    exit 1
fi
shift

BW="" ; DELAY="" ; JITTER="" ; LOSS="" ; CLEAR=0
while [ $# -gt 0 ]; do
    case "$1" in
        --bw)     BW="$2"; shift 2 ;;
        --delay)  DELAY="$2"; shift 2 ;;
        --jitter) JITTER="$2"; shift 2 ;;
        --loss)   LOSS="$2"; shift 2 ;;
        --clear)  CLEAR=1; shift ;;
        *) echo "[ERRO] Opção desconhecida: $1"; exit 1 ;;
    esac
done

tc qdisc del dev "$IFACE" root 2>/dev/null || true

if [ "$CLEAR" -eq 1 ]; then
    echo "[OK] Degradação removida de $IFACE"
    exit 0
fi

if [ -n "$DELAY" ] || [ -n "$JITTER" ] || [ -n "$LOSS" ]; then
    CMD="tc qdisc add dev $IFACE root handle 1: netem"
    if [ -n "$DELAY" ]; then
        CMD="$CMD delay $DELAY"
        [ -n "$JITTER" ] && CMD="$CMD $JITTER distribution normal"
    elif [ -n "$JITTER" ]; then
        CMD="$CMD delay 0ms $JITTER distribution normal"
    fi
    [ -n "$LOSS" ] && CMD="$CMD loss ${LOSS}%"
    echo "[INFO] $CMD"
    eval "$CMD"
    if [ -n "$BW" ]; then
        echo "[INFO] tc qdisc add dev $IFACE parent 1: handle 2: tbf rate ${BW}mbit burst 32kbit latency 400ms"
        tc qdisc add dev "$IFACE" parent 1: handle 2: tbf rate "${BW}mbit" burst 32kbit latency 400ms
    fi
elif [ -n "$BW" ]; then
    echo "[INFO] tc qdisc add dev $IFACE root handle 1: tbf rate ${BW}mbit burst 32kbit latency 400ms"
    tc qdisc add dev "$IFACE" root handle 1: tbf rate "${BW}mbit" burst 32kbit latency 400ms
else
    echo "[AVISO] Nenhum parâmetro de degradação informado."
fi

echo "[OK] Estado atual de $IFACE:"
tc qdisc show dev "$IFACE"
