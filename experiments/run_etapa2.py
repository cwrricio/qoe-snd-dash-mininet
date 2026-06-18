#!/usr/bin/env python3
"""Orquestrador dos experimentos da Etapa 2.

Para cada cenário (baseline + cenários adversos), o script:

  1. aplica degradação no enlace servidor->switch com `tc` (netem/tbf):
     limitação de banda, atraso, jitter e perda;
  2. opcionalmente gera tráfego concorrente com `iperf`;
  3. coleta métricas de rede (RTT/perda via ping, vazão via iperf);
  4. executa o cliente DASH headless e coleta métricas de QoE;
  5. salva tudo em results/etapa2/<cenario>.json.

Executar como root (Mininet exige):

    sudo python3 experiments/run_etapa2.py
"""

import argparse
import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from mininet.net import Mininet            # noqa: E402
from mininet.node import RemoteController, OVSController, OVSSwitch  # noqa: E402
from mininet.link import TCLink            # noqa: E402
from mininet.log import setLogLevel, info  # noqa: E402

from topology.topo_dash import DashTopo    # noqa: E402
from experiments.netimpair import (        # noqa: E402
    build_tc_commands, clear_tc_command, parse_ping, parse_iperf,
    restore_ownership,
)

SERVER_IP = "10.0.0.1"
HTTP_PORT = 8000
IPERF_PORT = 5001
MPD_URL = "http://%s:%d/output.mpd" % (SERVER_IP, HTTP_PORT)

RESULTS_DIR = os.path.join(PROJECT_DIR, "results", "etapa2")
QOE_DIR = os.path.join(RESULTS_DIR, "qoe")
NET_DIR = os.path.join(RESULTS_DIR, "net")

# Definição dos cenários. bw em Mbps; delay/jitter como string de tc; loss em %.
# cross_traffic = número de clientes extras saturando o link durante o teste.
SCENARIOS = [
    {"name": "baseline", "desc": "Sem degradação (referência)",
     "bw": None, "delay": None, "jitter": None, "loss": None, "cross_traffic": 0},
    {"name": "banda_baixa", "desc": "Banda limitada a 3 Mbps",
     "bw": 3, "delay": None, "jitter": None, "loss": None, "cross_traffic": 0},
    {"name": "atraso_alto", "desc": "Atraso de 150 ms",
     "bw": None, "delay": "150ms", "jitter": None, "loss": None, "cross_traffic": 0},
    {"name": "jitter", "desc": "Atraso 50 ms com jitter de 30 ms",
     "bw": None, "delay": "50ms", "jitter": "30ms", "loss": None, "cross_traffic": 0},
    {"name": "perda", "desc": "Perda de pacotes de 5%",
     "bw": None, "delay": None, "jitter": None, "loss": 5, "cross_traffic": 0},
    {"name": "congestionamento", "desc": "Link de 10 Mbps com 2 fluxos iperf concorrentes",
     "bw": 10, "delay": None, "jitter": None, "loss": None, "cross_traffic": 2},
    {"name": "combinado", "desc": "3 Mbps + 100 ms + 2% de perda",
     "bw": 3, "delay": "100ms", "jitter": None, "loss": 2, "cross_traffic": 0},
]


def apply_impairment(node, intf, bw=None, delay=None, jitter=None, loss=None):
    """Aplica netem (atraso/jitter/perda) e/ou tbf (banda) na saída de `intf`."""
    for cmd in build_tc_commands(intf, bw=bw, delay=delay, jitter=jitter, loss=loss):
        node.cmd(cmd)


def clear_impairment(node, intf):
    node.cmd(clear_tc_command(intf))


def collect_net_metrics(client, net_prefix):
    """Mede RTT/perda (ping) e vazão (iperf) do cliente até o servidor."""
    ping_out = client.cmd("ping -c 10 -i 0.3 %s" % SERVER_IP)
    with open(net_prefix + "_ping.txt", "w") as f:
        f.write(ping_out)
    rtt_avg, loss = parse_ping(ping_out)

    iperf_out = client.cmd("iperf -c %s -p %d -t 5" % (SERVER_IP, IPERF_PORT))
    with open(net_prefix + "_iperf.txt", "w") as f:
        f.write(iperf_out)
    throughput = parse_iperf(iperf_out)

    return {"rtt_avg_ms": rtt_avg, "loss_pct": loss, "throughput_mbps": throughput}


def run_scenario(net, scenario, client_name="h2", duration_guard=180):
    info("\n========== Cenário: %s ==========\n" % scenario["name"])
    info("[INFO] %s\n" % scenario["desc"])

    h1 = net.get("h1")
    client = net.get(client_name)
    srv_intf = h1.defaultIntf().name

    apply_impairment(h1, srv_intf,
                     bw=scenario["bw"], delay=scenario["delay"],
                     jitter=scenario["jitter"], loss=scenario["loss"])

    # Tráfego concorrente (congestionamento) durante todo o teste.
    cross_hosts = []
    if scenario["cross_traffic"] > 0:
        candidates = [h for h in ("h3", "h4") if h != client_name]
        cross_hosts = [net.get(candidates[i]) for i in range(scenario["cross_traffic"])]
        for ch in cross_hosts:
            ch.cmd("iperf -c %s -p %d -t %d > /tmp/cross_%s.log 2>&1 &"
                   % (SERVER_IP, IPERF_PORT, duration_guard, ch.name))
        info("[INFO] Tráfego concorrente iniciado em: %s\n"
             % ", ".join(h.name for h in cross_hosts))
        time.sleep(2)

    net_prefix = os.path.join(NET_DIR, scenario["name"])
    net_metrics = collect_net_metrics(client, net_prefix)
    info("[INFO] Rede: RTT=%s ms, perda=%s%%, vazão=%s Mbps\n"
         % (net_metrics["rtt_avg_ms"], net_metrics["loss_pct"],
            net_metrics["throughput_mbps"]))

    qoe_out = os.path.join(QOE_DIR, scenario["name"] + ".json")
    client_cmd = ("python3 %s --url %s --out %s --timeout 20"
                  % (os.path.join(PROJECT_DIR, "experiments", "dash_client.py"),
                     MPD_URL, qoe_out))
    info("[INFO] Executando cliente DASH...\n")
    client.cmd(client_cmd)

    qoe = {}
    if os.path.exists(qoe_out):
        with open(qoe_out) as f:
            qoe = json.load(f)
        info("[INFO] QoE: início=%ss, rebuffer=%s eventos/%ss, bitrate=%s kbps\n"
             % (qoe.get("startup_time_s"), qoe.get("rebuffer_events"),
                qoe.get("rebuffer_time_s"), qoe.get("avg_bitrate_kbps")))
    else:
        info("[WARN] Cliente DASH não gerou saída.\n")

    # Encerra tráfego concorrente e limpa a degradação. Os hosts compartilham
    # o namespace de PID, então mata-se apenas os clientes (iperf -c), preservando
    # o servidor (iperf -s) do h1.
    if cross_hosts:
        cross_hosts[0].cmd("pkill -f 'iperf -c' 2>/dev/null")
    clear_impairment(h1, srv_intf)

    return {
        "scenario": scenario["name"],
        "description": scenario["desc"],
        "params": {k: scenario[k] for k in ("bw", "delay", "jitter", "loss", "cross_traffic")},
        "net": net_metrics,
        "qoe": qoe,
    }


def main():
    ap = argparse.ArgumentParser(description="Orquestrador de experimentos da Etapa 2.")
    ap.add_argument("--controller", choices=["ovs", "remote"], default="ovs",
                    help="ovs = controlador de referência embutido (1 comando); "
                         "remote = POX externo na porta 6633 (igual à Etapa 1)")
    ap.add_argument("--client", default="h2", help="Host cliente que reproduz o vídeo")
    ap.add_argument("--only", help="Executar apenas um cenário (nome)")
    args = ap.parse_args()

    os.makedirs(QOE_DIR, exist_ok=True)
    os.makedirs(NET_DIR, exist_ok=True)

    dash_dir = os.path.join(PROJECT_DIR, "media", "dash")
    if not os.path.exists(os.path.join(dash_dir, "output.mpd")):
        info("[ERRO] media/dash/output.mpd não encontrado. Rode 'make video' antes.\n")
        sys.exit(1)

    net = Mininet(topo=DashTopo(), controller=None, switch=OVSSwitch,
                  link=TCLink, autoSetMacs=True)
    if args.controller == "remote":
        net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)
    else:
        net.addController("c0", controller=OVSController)

    net.start()
    info("\n[INFO] Aguardando convergência da rede...\n")
    net.pingAll()

    h1 = net.get("h1")
    info("[INFO] Iniciando servidor HTTP (DASH) e iperf no h1...\n")
    h1.cmd("cd %s && python3 -m http.server %d > /tmp/http_dash.log 2>&1 &"
           % (dash_dir, HTTP_PORT))
    h1.cmd("iperf -s -p %d > /tmp/iperf_srv.log 2>&1 &" % IPERF_PORT)
    time.sleep(2)

    scenarios = SCENARIOS
    if args.only:
        scenarios = [s for s in SCENARIOS if s["name"] == args.only]
        if not scenarios:
            info("[ERRO] Cenário '%s' não existe.\n" % args.only)
            net.stop()
            sys.exit(1)

    results = {}
    for scenario in scenarios:
        results[scenario["name"]] = run_scenario(net, scenario, client_name=args.client)

    # Mescla com um summary.json existente, para que rodar com --only não
    # apague os resultados dos demais cenários. A ordem segue SCENARIOS.
    summary_path = os.path.join(RESULTS_DIR, "summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path) as f:
                for entry in json.load(f):
                    results.setdefault(entry["scenario"], entry)
        except (ValueError, KeyError):
            pass
    order = [s["name"] for s in SCENARIOS]
    summary = [results[name] for name in order if name in results]
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    info("\n[OK] Resumo salvo em %s\n" % summary_path)

    net.stop()

    # Devolve a posse dos resultados ao usuário (rodamos via sudo).
    restore_ownership(os.path.join(PROJECT_DIR, "results"))


if __name__ == "__main__":
    setLogLevel("info")
    main()
