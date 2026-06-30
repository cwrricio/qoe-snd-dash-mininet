#!/usr/bin/env python3
"""Logica pura de controle de QoE via SDN (Etapa 3).

Funcoes testáveis sem Mininet, POX ou root. Quem executa as acoes
(instalar fluxos, aplicar tc) e o orquestrador run_etapa3.py.

Mecanismo de controle:
  1. Coletar bytes transmitidos no enlace gargalo (s1-eth2) periodicamente.
  2. Calcular a utilizacao do enlace (link_utilization_mbps).
  3. Detectar congestionamento quando a utilizacao ultrapassa o limiar.
  4. Quando congestionado e modo com_controle:
       a. Aplicar tc HTB em h1-eth0: garante banda minima ao video (h2) e
          limita o trafego concorrente.
       b. Instalar regra OpenFlow de alta prioridade via ovs-ofctl.
"""

# Porta HTTP onde o servidor serve o conteudo DASH.
DASH_PORT = 8000

# Fração da capacidade do enlace que dispara a deteccao de congestionamento.
DEFAULT_THRESHOLD = 0.8


def link_utilization_mbps(prev_bytes, curr_bytes, interval_s):
    """Utilizacao media (Mbps) entre duas leituras de contador de bytes.

    Retorna 0.0 se o contador reiniciou (curr < prev) ou o intervalo for
    nao positivo.
    """
    if interval_s <= 0:
        return 0.0
    delta = curr_bytes - prev_bytes
    if delta < 0:
        return 0.0
    return (delta * 8.0) / (interval_s * 1e6)


def is_congested(util_mbps, capacity_mbps, threshold=DEFAULT_THRESHOLD):
    """True quando a utilizacao atinge `threshold` da capacidade do enlace."""
    if capacity_mbps <= 0:
        return False
    return util_mbps >= threshold * capacity_mbps


def make_decision(util_mbps, capacity_mbps, mitigate=True,
                  threshold=DEFAULT_THRESHOLD):
    """Decide a acao de controle para uma leitura de utilizacao do enlace.

    Retorna um dicionario com:
      - congested: se o enlace esta congestionado;
      - action: 'prioritize_dash' (quando mitigate=True e congestionado)
                ou 'monitor' (caso contrario);
      - util_mbps / capacity_mbps / threshold_mbps: evidencia da decisao.

    Com mitigate=False o controlador apenas observa (modo sem_controle),
    permitindo comparar QoE com e sem controle usando o mesmo codigo.
    """
    congested = is_congested(util_mbps, capacity_mbps, threshold)
    action = "prioritize_dash" if (mitigate and congested) else "monitor"
    return {
        "congested":       congested,
        "action":          action,
        "util_mbps":       round(util_mbps, 3),
        "capacity_mbps":   capacity_mbps,
        "threshold_mbps":  round(threshold * capacity_mbps, 3),
    }


def format_decision_log(timestamp, dpid, port_no, decision):
    """Formata uma linha de log de decisao para results/etapa3/decisions.log."""
    return ("[%s] dpid=%s port=%s util=%.3f/%.1f Mbps congested=%s action=%s"
            % (timestamp, dpid, port_no, decision["util_mbps"],
               decision["capacity_mbps"], decision["congested"],
               decision["action"]))


def tc_priority_commands(intf, client_ip, capacity_mbps, dash_min_mbps):
    """Comandos tc HTB que priorizam o trafego DASH em `intf`.

    Cria dois classes HTB:
      - 1:11 (DASH, para client_ip): rate=dash_min_mbps garantido;
      - 1:12 (cross-traffic, default): rate=1Mbps, ceil=2Mbps.

    Retorna lista de comandos na ordem de execucao.
    """
    cap = int(capacity_mbps)
    dash = int(dash_min_mbps)
    return [
        "tc qdisc del dev %s root 2>/dev/null" % intf,
        "tc qdisc add dev %s root handle 1: htb default 12" % intf,
        "tc class add dev %s parent 1: classid 1:1 htb rate %dmbit" % (intf, cap),
        "tc class add dev %s parent 1:1 classid 1:11 htb rate %dmbit ceil %dmbit prio 0"
        % (intf, dash, cap),
        "tc class add dev %s parent 1:1 classid 1:12 htb rate 1mbit ceil 2mbit prio 1"
        % intf,
        "tc filter add dev %s parent 1: protocol ip prio 1 "
        "u32 match ip dst %s/32 flowid 1:11" % (intf, client_ip),
    ]


def tc_clear_command(intf):
    """Comando que remove o HTB de `intf` (idempotente)."""
    return "tc qdisc del dev %s root 2>/dev/null" % intf


def ofctl_add_dash_flow(switch_name, dash_port=DASH_PORT):
    """Comando ovs-ofctl que instala a regra OpenFlow de prioridade para DASH."""
    return ("ovs-ofctl add-flow %s "
            "priority=200,ip,nw_proto=6,tp_src=%d,actions=normal"
            % (switch_name, dash_port))


def ofctl_del_dash_flow(switch_name, dash_port=DASH_PORT):
    """Comando ovs-ofctl que remove a regra OpenFlow de prioridade para DASH."""
    return ("ovs-ofctl del-flows %s "
            "ip,nw_proto=6,tp_src=%d" % (switch_name, dash_port))
