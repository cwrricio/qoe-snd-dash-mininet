#!/bin/bash

echo "[INFO] Limpando ambiente Mininet..."
sudo mn -c

echo "[INFO] Encerrando processos auxiliares..."
sudo pkill -f ryu-manager || true
sudo pkill -f "python3 -m http.server" || true
sudo pkill -f iperf || true
sudo pkill -f tcpdump || true

echo "[OK] Ambiente limpo."