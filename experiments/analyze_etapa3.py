#!/usr/bin/env python3
"""Analise da Etapa 3 — comparacao baseline (sem controle) vs. com controle.

Le results/etapa3/summary.json (gerado por run_etapa3.py), consolida as
metricas de rede e QoE em um CSV e gera graficos comparando os dois modos,
evidenciando o ganho de QoE obtido com a priorizacao via SDN.

    python3 experiments/analyze_etapa3.py
"""

import csv
import json
import os
import sys


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_DIR, "results", "etapa3")
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")

MODE_LABELS = {"sem_controle": "Sem controle", "com_controle": "Com controle SDN"}

CSV_COLUMNS = [
    "mode", "description",
    "rtt_avg_ms", "loss_pct", "throughput_mbps",
    "startup_time_s", "rebuffer_events", "rebuffer_time_s",
    "avg_bitrate_kbps", "bitrate_switches", "mean_throughput_mbps",
]


def load_summary():
    path = os.path.join(RESULTS_DIR, "summary.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def flatten(entry):
    net = entry.get("net") or {}
    qoe = entry.get("qoe") or {}
    return {
        "mode": entry.get("mode", "?"),
        "description": entry.get("description", ""),
        "rtt_avg_ms": net.get("rtt_avg_ms"),
        "loss_pct": net.get("loss_pct"),
        "throughput_mbps": net.get("throughput_mbps"),
        "startup_time_s": qoe.get("startup_time_s"),
        "rebuffer_events": qoe.get("rebuffer_events"),
        "rebuffer_time_s": qoe.get("rebuffer_time_s"),
        "avg_bitrate_kbps": qoe.get("avg_bitrate_kbps"),
        "bitrate_switches": qoe.get("bitrate_switches"),
        "mean_throughput_mbps": qoe.get("mean_throughput_mbps"),
    }


def improvement(rows, key):
    """Variacao percentual de `key` de sem_controle -> com_controle.

    Retorna None se faltar algum dos dois valores ou se a base for zero.
    """
    by_mode = {r["mode"]: r for r in rows}
    base = by_mode.get("sem_controle", {}).get(key)
    ctrl = by_mode.get("com_controle", {}).get(key)
    if base is None or ctrl is None or base == 0:
        return None
    return (ctrl - base) / base * 100.0


def write_csv(rows):
    path = os.path.join(RESULTS_DIR, "summary.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print("[OK] CSV salvo em %s" % path)


def compare_bar(rows, key, ylabel, title, filename, color="#2e86c1"):
    data = [(MODE_LABELS.get(r["mode"], r["mode"]), r[key])
            for r in rows if r[key] is not None]
    if not data:
        return
    plt = _plt()
    labels = [d[0] for d in data]
    values = [d[1] for d in data]
    plt.figure(figsize=(6, 4.5))
    bars = plt.bar(labels, values, color=color)
    plt.ylabel(ylabel)
    plt.title(title)
    for b, v in zip(bars, values):
        plt.text(b.get_x() + b.get_width() / 2, v, "%.1f" % v,
                 ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, filename)
    plt.savefig(out, dpi=130)
    plt.close()
    print("[OK] %s" % out)


def main():
    os.makedirs(PLOTS_DIR, exist_ok=True)
    summary = load_summary()
    if not summary:
        print("[ERRO] Nenhum resultado em %s. Rode 'make etapa3' antes." % RESULTS_DIR)
        sys.exit(1)

    rows = [flatten(e) for e in summary]
    write_csv(rows)

    compare_bar(rows, "rebuffer_time_s", "Tempo de rebuffering (s)",
                "Rebuffering: sem vs. com controle", "cmp_rebuffer.png", "#e67e22")
    compare_bar(rows, "avg_bitrate_kbps", "Bitrate medio (kbps)",
                "Bitrate medio: sem vs. com controle", "cmp_bitrate.png", "#27ae60")
    compare_bar(rows, "startup_time_s", "Tempo de inicio (s)",
                "Tempo de inicio: sem vs. com controle", "cmp_startup.png", "#2e86c1")
    compare_bar(rows, "mean_throughput_mbps", "Vazao de download (Mbps)",
                "Vazao do streaming: sem vs. com controle", "cmp_throughput.png", "#8e44ad")

    print("\n[RESUMO] Ganho com o controle SDN (sem_controle -> com_controle):")
    for key, label, better in [
            ("startup_time_s", "Tempo de inicio", "menor"),
            ("rebuffer_time_s", "Tempo de rebuffering", "menor"),
            ("avg_bitrate_kbps", "Bitrate medio", "maior"),
            ("mean_throughput_mbps", "Vazao de download", "maior")]:
        delta = improvement(rows, key)
        if delta is not None:
            print("  - %-22s %+.1f%% (melhor = %s)" % (label + ":", delta, better))

    print("\n[OK] Analise concluida. Graficos em %s" % PLOTS_DIR)


if __name__ == "__main__":
    main()
