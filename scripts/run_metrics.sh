#!/bin/bash

mkdir -p results/ping results/iperf

echo "[INFO] Este script deve ser executado dentro do CLI do Mininet com comandos equivalentes:"
echo ""
echo "h2 ping -c 10 10.0.0.1 > results/ping/h2_to_h1.txt"
echo "h3 ping -c 10 10.0.0.1 > results/ping/h3_to_h1.txt"
echo "h4 ping -c 10 10.0.0.1 > results/ping/h4_to_h1.txt"
echo ""
echo "h1 iperf -s > results/iperf/server_h1.txt &"
echo "h2 iperf -c 10.0.0.1 -t 10 > results/iperf/h2_to_h1.txt"
echo "h3 iperf -c 10.0.0.1 -t 10 > results/iperf/h3_to_h1.txt"
echo "h4 iperf -c 10.0.0.1 -t 10 > results/iperf/h4_to_h1.txt"