#!/usr/bin/env python3
"""Orquestrador da Etapa 3 — Controle via SDN (mitigacao de degradacao).

Compara a QoE do streaming MPEG-DASH sob congestionamento em dois modos:

  - sem_controle: controlador so encaminha (baseline da Etapa 3);
  - com_controle: controlador detecta congestionamento e prioriza o DASH.

Cenario: enlace gargalo s1-eth2 limitado a CAPACITY_MBPS Mbps (tc tbf) e
CROSS_FLOWS fluxos iperf concorrentes (h1 -> h3/h4) competindo com o
streaming (h1 -> h2) durante toda a reproducao.

Laco de controle (classe SDNController, thread separada):
  1. Coleta periodicamente os bytes transmitidos em s1-eth2 via
     /sys/class/net/<intf>/statistics/tx_bytes.
  2. Calcula a utilizacao do enlace usando a logica pura de qoe_control.py.
  3. Quando congestionado E modo com_controle:
       a. Aplica tc HTB em h1-eth0: garante 8 Mbps para o cliente DASH (h2)
          e limita o trafego concorrente a 2 Mbps total.
       b. Instala uma regra OpenFlow de alta prioridade no switch s1 via
          ovs-ofctl, marcando o fluxo DASH (TCP porta 8000).
  4. Registra cada decisao em results/etapa3/decisions.log.

Executar como root (Mininet exige):

    sudo python3 experiments/run_etapa3.py            # roda os dois modos
    sudo python3 experiments/run_etapa3.py --mode com_controle
"""

import argparse
import json
import os
import sys
import threading
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from mininet.net import Mininet                                  # noqa: E402
from mininet.node import OVSController, OVSSwitch               # noqa: E402
from mininet.link import TCLink                                  # noqa: E402
from mininet.log import setLogLevel, info                        # noqa: E402

from topology.topo_dash import DashTopo                          # noqa: E402
from experiments.netimpair import parse_ping, parse_iperf, restore_ownership  # noqa: E402
from experiments import qoe_control                              # noqa: E402

SERVER_IP    = "10.0.0.1"
CLIENT_IP    = "10.0.0.2"   # h2 — cliente de video
HTTP_PORT    = 8000
IPERF_PORT   = 5001
MPD_URL      = "http://%s:%d/output.mpd" % (SERVER_IP, HTTP_PORT)

BOTTLENECK_INTF = "s1-eth2"   # saida de s1 para s2 — gargalo
BOTTLENECK_PORT = 2
CAPACITY_MBPS   = 10          # limite imposto no gargalo
DASH_MIN_MBPS   = 8           # banda minima garantida ao video no controle
CROSS_FLOWS     = 2           # fluxos iperf concorrentes (h3, h4)

RESULTS_DIR = os.path.join(PROJECT_DIR, "results", "etapa3")
QOE_DIR     = os.path.join(RESULTS_DIR, "qoe")
NET_DIR     = os.path.join(RESULTS_DIR, "net")
LOG_PATH    = os.path.join(RESULTS_DIR, "decisions.log")

MODES = {
    "sem_controle": {"mitigate": False,
                     "desc": "Congestionamento sem controle (baseline da Etapa 3)"},
    "com_controle": {"mitigate": True,
                     "desc": "Congestionamento com priorizacao DASH via SDN"},
}


# ---------------------------------------------------------------------------
# Laco de controle SDN (roda em thread separada durante o experimento)
# ---------------------------------------------------------------------------

class SDNController:
    """Detecta congestionamento em s1-eth2 e age sobre o streaming DASH."""

    POLL_INTERVAL = 2.0

    def __init__(self, net, mitigate, capacity_mbps, log_path):
        self.net          = net
        self.mitigate     = mitigate
        self.capacity_mbps = capacity_mbps
        self.log_path     = log_path
        self._stop        = threading.Event()
        self._prev_bytes  = None
        self._prev_time   = None
        self._mitigating  = False

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        if self._mitigating:
            self._remove_priority()

    # --- loop principal ---

    def _loop(self):
        while not self._stop.wait(self.POLL_INTERVAL):
            now = time.time()
            tx  = self._read_tx_bytes()
            if tx is None:
                continue
            if self._prev_bytes is not None:
                util     = qoe_control.link_utilization_mbps(
                    self._prev_bytes, tx, now - self._prev_time)
                decision = qoe_control.make_decision(
                    util, self.capacity_mbps, mitigate=self.mitigate)
                self._record(decision)
                self._act(decision)
            self._prev_bytes = tx
            self._prev_time  = now

    def _read_tx_bytes(self):
        try:
            with open("/sys/class/net/%s/statistics/tx_bytes" % BOTTLENECK_INTF) as f:
                return int(f.read().strip())
        except (IOError, ValueError):
            return None

    # --- acao de controle ---

    def _act(self, decision):
        if decision["action"] == "prioritize_dash" and not self._mitigating:
            self._mitigating = True
            self._apply_priority()
            info("[CONTROLE] Congestionamento detectado (%.2f/%.1f Mbps) "
                 "— priorizando DASH\n"
                 % (decision["util_mbps"], decision["capacity_mbps"]))
        elif decision["action"] == "monitor" and self._mitigating:
            self._mitigating = False
            self._remove_priority()
            info("[CONTROLE] Enlace normalizado — prioridade DASH removida\n")

    def _apply_priority(self):
        h1   = self.net.get("h1")
        intf = "h1-eth0"
        cap  = int(self.capacity_mbps)
        # HTB em h1-eth0: garante DASH_MIN_MBPS para h2, limita cross-traffic.
        h1.cmd("tc qdisc del dev %s root 2>/dev/null" % intf)
        h1.cmd("tc qdisc add dev %s root handle 1: htb default 12" % intf)
        h1.cmd("tc class add dev %s parent 1: classid 1:1  htb rate %dmbit"
               % (intf, cap))
        h1.cmd("tc class add dev %s parent 1:1 classid 1:11 htb "
               "rate %dmbit ceil %dmbit prio 0"
               % (intf, DASH_MIN_MBPS, cap))
        h1.cmd("tc class add dev %s parent 1:1 classid 1:12 htb "
               "rate 1mbit ceil 2mbit prio 1" % intf)
        h1.cmd("tc filter add dev %s parent 1: protocol ip prio 1 "
               "u32 match ip dst %s/32 flowid 1:11" % (intf, CLIENT_IP))

        # Regra OpenFlow de alta prioridade para o fluxo DASH (porta 8000).
        s1 = self.net.get("s1")
        s1.cmd("ovs-ofctl add-flow s1 "
               "priority=200,ip,nw_proto=6,tp_src=%d,actions=normal"
               % qoe_control.DASH_PORT)

    def _remove_priority(self):
        h1 = self.net.get("h1")
        h1.cmd("tc qdisc del dev h1-eth0 root 2>/dev/null")
        s1 = self.net.get("s1")
        s1.cmd("ovs-ofctl del-flows s1 "
               "ip,nw_proto=6,tp_src=%d" % qoe_control.DASH_PORT)

    # --- log ---

    def _record(self, decision):
        line = qoe_control.format_decision_log(
            time.strftime("%Y-%m-%d %H:%M:%S"), "s1", BOTTLENECK_PORT, decision)
        info(line + "\n")
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            info("[WARN] Nao foi possivel gravar decisions.log: %s\n" % exc)


# ---------------------------------------------------------------------------
# Coleta de metricas de rede
# ---------------------------------------------------------------------------

def collect_net_metrics(client, net_prefix):
    ping_out = client.cmd("ping -c 10 -i 0.3 %s" % SERVER_IP)
    with open(net_prefix + "_ping.txt", "w") as f:
        f.write(ping_out)
    rtt_avg, loss = parse_ping(ping_out)

    iperf_out = client.cmd("iperf -c %s -p %d -t 5" % (SERVER_IP, IPERF_PORT))
    with open(net_prefix + "_iperf.txt", "w") as f:
        f.write(iperf_out)
    throughput = parse_iperf(iperf_out)
    return {"rtt_avg_ms": rtt_avg, "loss_pct": loss, "throughput_mbps": throughput}


# ---------------------------------------------------------------------------
# Execucao de um modo (sem_controle ou com_controle)
# ---------------------------------------------------------------------------

def run_mode(mode, client_name="h2", duration_guard=120):
    cfg = MODES[mode]
    info("\n========== Modo: %s ==========\n" % mode)
    info("[INFO] %s\n" % cfg["desc"])

    net = Mininet(topo=DashTopo(), controller=None, switch=OVSSwitch,
                  link=TCLink, autoSetMacs=True)
    net.addController("c0", controller=OVSController)
    net.start()
    info("[INFO] Aguardando convergencia da rede...\n")
    net.pingAll()

    h1     = net.get("h1")
    s1     = net.get("s1")
    client = net.get(client_name)

    # Cria o gargalo de 10 Mbps em s1-eth2 (simula enlace de acesso limitado).
    s1.cmd("tc qdisc del dev %s root 2>/dev/null" % BOTTLENECK_INTF)
    s1.cmd("tc qdisc add dev %s root handle 1: tbf "
           "rate %dmbit burst 32kbit latency 400ms"
           % (BOTTLENECK_INTF, CAPACITY_MBPS))
    info("[INFO] Gargalo de %d Mbps aplicado em %s\n"
         % (CAPACITY_MBPS, BOTTLENECK_INTF))

    dash_dir = os.path.join(PROJECT_DIR, "media", "dash")
    h1.cmd("cd %s && python3 -m http.server %d > /tmp/http_dash.log 2>&1 &"
           % (dash_dir, HTTP_PORT))
    h1.cmd("iperf -s -p %d > /tmp/iperf_srv.log 2>&1 &" % IPERF_PORT)
    time.sleep(1)

    # Trafego concorrente: h1 envia para h3/h4 via iperf, saturando o gargalo.
    cross = [net.get(h) for h in ("h3", "h4")][:CROSS_FLOWS]
    for ch in cross:
        ch.cmd("iperf -s -p %d > /tmp/iperf_%s.log 2>&1 &"
               % (IPERF_PORT, ch.name))
    time.sleep(1)
    for ch in cross:
        h1.cmd("iperf -c %s -p %d -t %d > /tmp/cross_%s.log 2>&1 &"
               % (ch.IP(), IPERF_PORT, duration_guard, ch.name))
    info("[INFO] Trafego concorrente (h1 -> %s) iniciado.\n"
         % ", ".join(c.name for c in cross))

    # Inicia o laco de controle SDN.
    ctrl = SDNController(net, cfg["mitigate"], CAPACITY_MBPS, LOG_PATH)
    ctrl.start()
    time.sleep(3)  # deixa o congestionamento e o controle se estabelecerem

    net_prefix  = os.path.join(NET_DIR, mode)
    net_metrics = collect_net_metrics(client, net_prefix)
    info("[INFO] Rede: RTT=%s ms, perda=%s%%, vazao=%s Mbps\n"
         % (net_metrics["rtt_avg_ms"], net_metrics["loss_pct"],
            net_metrics["throughput_mbps"]))

    qoe_out = os.path.join(QOE_DIR, mode + ".json")
    info("[INFO] Executando cliente DASH...\n")
    client.cmd("python3 %s --url %s --out %s --timeout 20"
               % (os.path.join(PROJECT_DIR, "experiments", "dash_client.py"),
                  MPD_URL, qoe_out))

    qoe = {}
    if os.path.exists(qoe_out):
        with open(qoe_out) as f:
            qoe = json.load(f)
        info("[INFO] QoE: inicio=%ss, rebuffer=%s eventos/%ss, bitrate=%s kbps\n"
             % (qoe.get("startup_time_s"), qoe.get("rebuffer_events"),
                qoe.get("rebuffer_time_s"), qoe.get("avg_bitrate_kbps")))
    else:
        info("[WARN] Cliente DASH nao gerou saida.\n")

    ctrl.stop()
    h1.cmd("pkill -f 'iperf -c' 2>/dev/null")
    s1.cmd("tc qdisc del dev %s root 2>/dev/null" % BOTTLENECK_INTF)
    net.stop()

    return {
        "mode": mode,
        "description": cfg["desc"],
        "mitigate": cfg["mitigate"],
        "params": {
            "capacity_mbps":  CAPACITY_MBPS,
            "dash_min_mbps":  DASH_MIN_MBPS,
            "cross_flows":    CROSS_FLOWS,
            "bottleneck":     BOTTLENECK_INTF,
        },
        "net": net_metrics,
        "qoe": qoe,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Orquestrador da Etapa 3 (controle SDN de QoE).")
    ap.add_argument("--mode", choices=list(MODES),
                    help="Roda apenas um modo (padrao: ambos)")
    ap.add_argument("--client", default="h2",
                    help="Host cliente que reproduz o video")
    args = ap.parse_args()

    os.makedirs(QOE_DIR, exist_ok=True)
    os.makedirs(NET_DIR, exist_ok=True)

    if not os.path.exists(os.path.join(PROJECT_DIR, "media", "dash", "output.mpd")):
        info("[ERRO] media/dash/output.mpd nao encontrado. Rode 'make video'.\n")
        sys.exit(1)

    modes = [args.mode] if args.mode else list(MODES)
    results = {}
    for mode in modes:
        results[mode] = run_mode(mode, client_name=args.client)

    # Mescla com summary.json existente.
    summary_path = os.path.join(RESULTS_DIR, "summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path) as f:
                for entry in json.load(f):
                    results.setdefault(entry["mode"], entry)
        except (ValueError, KeyError):
            pass
    summary = [results[m] for m in MODES if m in results]
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    info("\n[OK] Resumo salvo em %s\n" % summary_path)

    restore_ownership(os.path.join(PROJECT_DIR, "results"))


if __name__ == "__main__":
    setLogLevel("info")
    main()
