#!/usr/bin/env python3
"""Funções puras de degradação de rede e parsing de métricas (Etapa 2).

Separadas do orquestrador (run_etapa2.py) para poderem ser testadas sem o
Mininet instalado. Aqui só se constrói os comandos `tc` e se interpreta a
saída de `ping`/`iperf`; quem executa os comandos é o orquestrador.
"""

import os
import re


def restore_ownership(path):
    """Devolve a posse de `path` (recursivo) ao usuário que chamou via sudo.

    Como o Mininet exige root, os resultados seriam criados como root e o
    `make analyze` (rodado como usuário comum) não conseguiria escrever neles.
    Sem SUDO_UID/SUDO_GID no ambiente, não faz nada.
    """
    sudo_uid = os.environ.get("SUDO_UID")
    sudo_gid = os.environ.get("SUDO_GID")
    if sudo_uid is None or sudo_gid is None or not os.path.exists(path):
        return
    uid, gid = int(sudo_uid), int(sudo_gid)
    for root, dirs, files in os.walk(path):
        for name in [""] + dirs + files:
            try:
                os.chown(os.path.join(root, name), uid, gid)
            except OSError:
                pass


def clear_tc_command(intf):
    """Comando que remove qualquer qdisc raiz da interface."""
    return "tc qdisc del dev %s root 2>/dev/null" % intf


def build_tc_commands(intf, bw=None, delay=None, jitter=None, loss=None):
    """Monta a sequência de comandos `tc` para a degradação pedida.

    Sempre começa limpando a interface. netem (atraso/jitter/perda) entra como
    qdisc raiz; quando há também limitação de banda, o tbf entra como filho.
    Se apenas banda for pedida, o tbf é a raiz.

    Devolve uma lista de strings de comando (na ordem de execução).
    """
    cmds = [clear_tc_command(intf)]
    if not any([bw, delay, jitter, loss]):
        return cmds

    use_netem = bool(delay or jitter or loss)
    if use_netem:
        netem = "tc qdisc add dev %s root handle 1: netem" % intf
        if delay:
            netem += " delay %s" % delay
            if jitter:
                netem += " %s distribution normal" % jitter
        elif jitter:
            netem += " delay 0ms %s distribution normal" % jitter
        if loss:
            netem += " loss %s%%" % loss
        cmds.append(netem)
        if bw:
            cmds.append("tc qdisc add dev %s parent 1: handle 2: tbf "
                        "rate %dmbit burst 32kbit latency 400ms" % (intf, bw))
    elif bw:
        cmds.append("tc qdisc add dev %s root handle 1: tbf "
                    "rate %dmbit burst 32kbit latency 400ms" % (intf, bw))
    return cmds


def parse_ping(output):
    """Extrai (rtt_avg_ms, loss_pct) da saída do ping. None quando ausente."""
    loss = None
    rtt_avg = None
    m = re.search(r"(\d+(?:\.\d+)?)% packet loss", output)
    if m:
        loss = float(m.group(1))
    m = re.search(r"=\s*[\d.]+/([\d.]+)/", output)
    if m:
        rtt_avg = float(m.group(1))
    return rtt_avg, loss


def parse_iperf(output):
    """Extrai a última vazão reportada pelo iperf, em Mbps. None se ausente."""
    vals = re.findall(r"([\d.]+)\s*Mbits/sec", output)
    if vals:
        return float(vals[-1])
    vals = re.findall(r"([\d.]+)\s*Kbits/sec", output)
    if vals:
        return float(vals[-1]) / 1000.0
    vals = re.findall(r"([\d.]+)\s*Gbits/sec", output)
    if vals:
        return float(vals[-1]) * 1000.0
    return None
