#!/usr/bin/env python3
"""Orquestrador da Etapa 3 — Controle via SDN (mitigacao de degradacao).

Compara a QoE do streaming MPEG-DASH sob congestionamento em dois modos:

  - sem_controle: POX ext.qoe_guard so encaminha/monitora;
  - com_controle: POX ext.qoe_guard detecta congestionamento e instala regra
    OpenFlow dinamica para priorizar o DASH.

Cenario: enlace gargalo s1-eth2 limitado a CAPACITY_MBPS Mbps (tc tbf) e
CROSS_FLOWS fluxos iperf concorrentes (h1 -> h3/h4) competindo com o
streaming (h1 -> h2) durante toda a reproducao.

Fluxo automatico:
  1. Inicia o controlador POX da Etapa 3 (ext.qoe_guard) no modo correto.
  2. Sobe a topologia Mininet conectada ao POX via RemoteController.
  3. Aplica gargalo e trafego concorrente.
  4. Um agente local aplica tc HTB no host servidor quando ha congestionamento,
     porque a fila de host Linux nao e configuravel pelo controlador OpenFlow.
  5. O POX registra as decisoes SDN em results/etapa3/decisions.log.

Executar como root (Mininet exige):

    sudo python3 experiments/run_etapa3.py            # roda os dois modos
    sudo python3 experiments/run_etapa3.py --mode com_controle
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from mininet.net import Mininet                                  # noqa: E402
from mininet.node import RemoteController, OVSController, OVSSwitch  # noqa: E402
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
QOS_LOG_PATH = os.path.join(RESULTS_DIR, "qos_decisions.log")
POX_DIR     = os.path.join(PROJECT_DIR, "tools", "pox")
POX_APP_SRC = os.path.join(PROJECT_DIR, "controller", "qoe_guard.py")
POX_APP_DST = os.path.join(POX_DIR, "ext", "qoe_guard.py")

MODES = {
    "sem_controle": {"mitigate": False,
                     "desc": "Congestionamento sem controle (baseline da Etapa 3)"},
    "com_controle": {"mitigate": True,
                     "desc": "Congestionamento com priorizacao DASH via SDN"},
}


# ---------------------------------------------------------------------------
# Controlador POX automatico
# ---------------------------------------------------------------------------

class PoxControllerProcess:
    """Processo POX ext.qoe_guard usado como controlador SDN da Etapa 3."""

    def __init__(self, mitigate, log_path):
        self.mitigate = mitigate
        self.log_path = log_path
        self.proc = None

    def start(self):
        pox_py = os.path.join(POX_DIR, "pox.py")
        if not os.path.exists(pox_py):
            raise RuntimeError(
                "POX nao encontrado em %s. Rode 'make install' antes." % POX_DIR)

        os.makedirs(os.path.dirname(POX_APP_DST), exist_ok=True)
        shutil.copy2(POX_APP_SRC, POX_APP_DST)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        cmd = [
            "python3", "pox.py", "ext.qoe_guard",
            "--mitigate=%s" % ("True" if self.mitigate else "False"),
            "--capacity=%s" % CAPACITY_MBPS,
            "--bottleneck=%s" % BOTTLENECK_INTF,
            "--port=%s" % BOTTLENECK_PORT,
            "--interval=2",
        ]
        log_f = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            cmd, cwd=POX_DIR, stdout=log_f, stderr=subprocess.STDOUT)
        self._log_f = log_f
        time.sleep(2)
        if self.proc.poll() is not None:
            self._log_f.close()
            raise RuntimeError(
                "POX encerrou durante a inicializacao. Veja %s" % self.log_path)
        info("[INFO] POX ext.qoe_guard iniciado (mitigate=%s, log=%s)\n"
             % (self.mitigate, self.log_path))

    def stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self._log_f.close()


# ---------------------------------------------------------------------------
# Agente de QoS de host (roda em thread separada durante o experimento)
# ---------------------------------------------------------------------------

class HostQoSAgent:
    """Aplica HTB em h1-eth0 quando o gargalo afeta o streaming DASH."""

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

    def _remove_priority(self):
        h1 = self.net.get("h1")
        h1.cmd("tc qdisc del dev h1-eth0 root 2>/dev/null")

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

def run_mode(mode, client_name="h2", duration_guard=120, controller="pox"):
    cfg = MODES[mode]
    info("\n========== Modo: %s ==========\n" % mode)
    info("[INFO] %s\n" % cfg["desc"])

    pox = None
    net = None
    if controller == "pox":
        pox_log = os.path.join(RESULTS_DIR, "pox_%s.log" % mode)
        pox = PoxControllerProcess(cfg["mitigate"], pox_log)
        pox.start()

    try:
        net = Mininet(topo=DashTopo(), controller=None, switch=OVSSwitch,
                      link=TCLink, autoSetMacs=True)
        if controller == "pox":
            net.addController("c0", controller=RemoteController,
                              ip="127.0.0.1", port=6633)
        else:
            net.addController("c0", controller=OVSController)
        net.start()
    except Exception:
        if net is not None:
            net.stop()
        if pox is not None:
            pox.stop()
        raise
    ctrl = None
    h1 = None
    s1 = None
    try:
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

        # Inicia o agente de QoS de host usado pela mitigacao da Etapa 3.
        qos_log = QOS_LOG_PATH if controller == "pox" else LOG_PATH
        ctrl = HostQoSAgent(net, cfg["mitigate"], CAPACITY_MBPS, qos_log)
        ctrl.start()
        time.sleep(3)  # deixa o congestionamento e a mitigacao se estabelecerem

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
    finally:
        if ctrl is not None:
            ctrl.stop()
        if h1 is not None:
            h1.cmd("pkill -f 'iperf -c' 2>/dev/null")
        if s1 is not None:
            s1.cmd("tc qdisc del dev %s root 2>/dev/null" % BOTTLENECK_INTF)
        if net is not None:
            net.stop()
        if pox is not None:
            pox.stop()

    return {
        "mode": mode,
        "description": cfg["desc"],
        "mitigate": cfg["mitigate"],
        "params": {
            "capacity_mbps":  CAPACITY_MBPS,
            "dash_min_mbps":  DASH_MIN_MBPS,
            "cross_flows":    CROSS_FLOWS,
            "bottleneck":     BOTTLENECK_INTF,
            "controller":     controller,
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
    ap.add_argument("--controller", choices=["pox", "ovs"], default="pox",
                    help="pox = ext.qoe_guard automatico (padrao da Etapa 3); "
                         "ovs = controlador embutido, apenas para depuracao")
    args = ap.parse_args()

    os.makedirs(QOE_DIR, exist_ok=True)
    os.makedirs(NET_DIR, exist_ok=True)

    if not os.path.exists(os.path.join(PROJECT_DIR, "media", "dash", "output.mpd")):
        info("[ERRO] media/dash/output.mpd nao encontrado. Rode 'make video'.\n")
        sys.exit(1)

    modes = [args.mode] if args.mode else list(MODES)
    results = {}
    for mode in modes:
        results[mode] = run_mode(mode, client_name=args.client,
                                 controller=args.controller)

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
    restore_ownership(os.path.dirname(POX_APP_DST))


if __name__ == "__main__":
    setLogLevel("info")
    main()
