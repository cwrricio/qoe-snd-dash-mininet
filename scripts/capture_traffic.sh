#!/bin/bash

mkdir -p results/pcap

INTERFACE="${1:-s1-eth1}"
OUTPUT="results/pcap/dash_capture_$(date +%Y%m%d_%H%M%S).pcap"

echo "[INFO] Capturando tráfego na interface $INTERFACE"
echo "[INFO] Arquivo de saída: $OUTPUT"
echo "[INFO] Pressione CTRL+C para encerrar."

sudo tcpdump -i "$INTERFACE" -w "$OUTPUT"