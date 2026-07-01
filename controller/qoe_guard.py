#!/usr/bin/env python3
"""Controlador SDN com mitigacao de degradacao de QoE (Etapa 3) — app POX.

Estende o encaminhamento L2 com um laco de controle que:

  1. coleta periodicamente *port stats* via OpenFlow (ofp_stats_request);
  2. calcula a utilizacao do enlace gargalo e detecta congestionamento
     (logica pura em experiments/qoe_control.py);
  3. quando congestionado e com mitigacao habilitada, instala dinamicamente
     uma regra OpenFlow de alta prioridade que encaminha o trafego de video
     (MPEG-DASH, TCP porta 8000) pela porta gargalo conhecida;
  4. registra cada decisao em results/etapa3/decisions.log.

Uso (a partir de tools/pox):

    PYTHONPATH=ext python3 pox.py qoe_guard                 # com mitigacao
    PYTHONPATH=ext python3 pox.py qoe_guard --mitigate=False # baseline
    PYTHONPATH=ext python3 pox.py qoe_guard --bottleneck=s1-eth2 --capacity=10

Parametros (todos opcionais):
    --mitigate    True/False — habilita a acao de priorizacao (padrao True)
    --capacity    capacidade do enlace gargalo em Mbps (padrao 10)
    --bottleneck  nome da interface gargalo, so para o log (padrao s1-eth2)
    --port        numero da porta de saida gargalo no switch s1 (padrao 2)
    --interval    periodo de coleta de stats em segundos (padrao 3)
"""

import os
import sys
import time

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpid_to_str
from pox.lib.recoco import Timer

# Importa a logica pura compartilhada (raiz do projeto = tools/pox/../..).
_PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from experiments import qoe_control  # noqa: E402

log = core.getLogger()

_DECISIONS_LOG = os.path.join(_PROJECT_DIR, "results", "etapa3", "decisions.log")


def _str2bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


class QoEGuard(object):
    """Switch L2 com aprendizado + laco de controle de QoE por datapath."""

    def __init__(self, connection, opts):
        self.connection = connection
        self.opts = opts
        self.macToPort = {}
        # Estado para o calculo de utilizacao entre coletas.
        self._prev_bytes = None
        self._prev_time = None
        # Evita reinstalar a regra de priorizacao a cada deteccao.
        self._mitigating = False
        connection.addListeners(self)

        # Apenas o switch de borda do servidor (s1, dpid 1) hospeda o gargalo.
        if connection.dpid == 1:
            Timer(opts["interval"], self._poll_stats, recurring=True)
            log.info("QoEGuard ativo no dpid %s (gargalo porta %s, %s Mbps, "
                     "mitigacao=%s)", connection.dpid, opts["port"],
                     opts["capacity"], opts["mitigate"])

    # ----- encaminhamento L2 (igual ao l2_learning) -----

    def _handle_PacketIn(self, event):
        packet = event.parsed
        self.macToPort[packet.src] = event.port

        if packet.dst.is_multicast:
            self._flood(event)
            return

        if packet.dst not in self.macToPort:
            self._flood(event)
            return

        out_port = self.macToPort[packet.dst]
        if out_port == event.port:
            self._drop(event)
            return

        # Instala fluxo reativo (camada 2) e encaminha o pacote atual.
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet, event.port)
        msg.idle_timeout = 10
        msg.hard_timeout = 30
        msg.actions.append(of.ofp_action_output(port=out_port))
        msg.data = event.ofp
        self.connection.send(msg)

    def _flood(self, event):
        msg = of.ofp_packet_out()
        msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
        msg.data = event.ofp
        msg.in_port = event.port
        self.connection.send(msg)

    def _drop(self, event):
        msg = of.ofp_packet_out()
        msg.in_port = event.port
        self.connection.send(msg)

    # ----- laco de controle de QoE -----

    def _poll_stats(self):
        """Pede as estatisticas de porta do switch periodicamente."""
        self.connection.send(of.ofp_stats_request(body=of.ofp_port_stats_request()))

    def _handle_PortStatsReceived(self, event):
        now = time.time()
        port_no = self.opts["port"]
        tx_bytes = None
        for stat in event.stats:
            if stat.port_no == port_no:
                tx_bytes = stat.tx_bytes
                break
        if tx_bytes is None:
            return

        if self._prev_bytes is not None:
            interval = now - self._prev_time
            util = qoe_control.link_utilization_mbps(
                self._prev_bytes, tx_bytes, interval)
            decision = qoe_control.make_decision(
                util, self.opts["capacity"], mitigate=self.opts["mitigate"])
            self._record(port_no, decision)
            self._act(decision)

        self._prev_bytes = tx_bytes
        self._prev_time = now

    def _act(self, decision):
        """Aplica/retira a priorizacao do video conforme a decisao."""
        if decision["action"] == "prioritize_dash":
            if not self._mitigating:
                self._install_dash_priority()
                self._mitigating = True
                log.warning("CONGESTIONAMENTO detectado — priorizando DASH "
                            "(util=%.2f Mbps)", decision["util_mbps"])
        else:
            if self._mitigating:
                self._mitigating = False
                self._remove_dash_priority()
                log.info("Enlace normalizado (util=%.2f Mbps)",
                         decision["util_mbps"])

    def _install_dash_priority(self):
        """Instala regra OpenFlow de alta prioridade para o video.

        Casa o trafego TCP cuja porta de origem e a porta HTTP do DASH (8000),
        ou seja, os segmentos de video saindo do servidor, e o encaminha pela
        porta gargalo conhecida. A priorizacao por banda do experimento
        reproduzivel fica no `tc HTB` aplicado por experiments/run_etapa3.py.
        """
        port_no = self.opts["port"]
        msg = of.ofp_flow_mod()
        msg.priority = 30000  # acima dos fluxos L2 reativos
        msg.match.dl_type = 0x0800       # IPv4
        msg.match.nw_proto = 6           # TCP
        msg.match.tp_src = qoe_control.DASH_PORT
        msg.actions.append(of.ofp_action_output(port=port_no))
        self.connection.send(msg)

    def _remove_dash_priority(self):
        """Remove a regra de priorizacao instalada pelo controlador."""
        msg = of.ofp_flow_mod()
        msg.command = of.OFPFC_DELETE
        msg.priority = 30000
        msg.match.dl_type = 0x0800
        msg.match.nw_proto = 6
        msg.match.tp_src = qoe_control.DASH_PORT
        self.connection.send(msg)

    def _record(self, port_no, decision):
        line = qoe_control.format_decision_log(
            time.strftime("%Y-%m-%d %H:%M:%S"),
            dpid_to_str(self.connection.dpid), port_no, decision)
        log.info(line)
        try:
            os.makedirs(os.path.dirname(_DECISIONS_LOG), exist_ok=True)
            with open(_DECISIONS_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            log.warning("Nao foi possivel gravar o log de decisoes: %s", exc)


class QoEGuardLauncher(object):
    def __init__(self, opts):
        self.opts = opts
        core.openflow.addListeners(self)

    def _handle_ConnectionUp(self, event):
        QoEGuard(event.connection, self.opts)


def launch(mitigate="True", capacity="10", bottleneck="s1-eth2",
           port="2", interval="3"):
    opts = {
        "mitigate": _str2bool(mitigate),
        "capacity": float(capacity),
        "bottleneck": bottleneck,
        "port": int(port),
        "interval": float(interval),
    }
    core.registerNew(QoEGuardLauncher, opts)
    log.info("ext.qoe_guard carregado (mitigacao=%s, gargalo=%s @ %s Mbps)",
             opts["mitigate"], bottleneck, capacity)
