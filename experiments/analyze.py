#!/usr/bin/env python3
"""Análise dos resultados da Etapa 2.

Lê results/etapa2/summary.json (gerado por run_etapa2.py), consolida as
métricas em um CSV e gera gráficos comparativos entre os cenários, além de
gráficos de correlação entre métricas de rede e métricas de QoE.

    python3 experiments/analyze.py
"""

import csv
import json
import os
import sys


def _plt():
    """Importa matplotlib sob demanda (backend Agg), para que as funções de
    dados possam ser usadas/testadas sem matplotlib instalado."""
    import matplotlib
    matplotlib.use("Agg")  # backend sem display, para rodar em VM/servidor
    import matplotlib.pyplot as plt
    return plt


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_DIR, "results", "etapa2")
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")

CSV_COLUMNS = [
    "scenario", "description",
    "rtt_avg_ms", "loss_pct", "throughput_mbps",
    "startup_time_s", "rebuffer_events", "rebuffer_time_s",
    "avg_bitrate_kbps", "bitrate_switches", "mean_throughput_mbps",
]


def load_summary():
    """Carrega summary.json, ou reconstrói a partir dos JSONs por cenário."""
    summary_path = os.path.join(RESULTS_DIR, "summary.json")
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            return json.load(f)

    qoe_dir = os.path.join(RESULTS_DIR, "qoe")
    if not os.path.isdir(qoe_dir):
        return []
    rebuilt = []
    for name in sorted(os.listdir(qoe_dir)):
        if name.endswith(".json"):
            with open(os.path.join(qoe_dir, name)) as f:
                rebuilt.append({"scenario": name[:-5], "qoe": json.load(f), "net": {}})
    return rebuilt


def flatten(entry):
    net = entry.get("net") or {}
    qoe = entry.get("qoe") or {}
    return {
        "scenario": entry.get("scenario", "?"),
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


def write_csv(rows):
    path = os.path.join(RESULTS_DIR, "summary.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print("[OK] CSV salvo em %s" % path)


def bar_chart(rows, key, ylabel, title, filename, color="#3b6fb0"):
    data = [(r["scenario"], r[key]) for r in rows if r[key] is not None]
    if not data:
        return
    plt = _plt()
    labels = [d[0] for d in data]
    values = [d[1] for d in data]
    plt.figure(figsize=(9, 4.5))
    bars = plt.bar(labels, values, color=color)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xticks(rotation=30, ha="right")
    for b, v in zip(bars, values):
        plt.text(b.get_x() + b.get_width() / 2, v, "%.1f" % v,
                 ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, filename)
    plt.savefig(out, dpi=130)
    plt.close()
    print("[OK] %s" % out)


def scatter_chart(rows, xkey, ykey, xlabel, ylabel, title, filename):
    pts = [(r[xkey], r[ykey], r["scenario"]) for r in rows
           if r[xkey] is not None and r[ykey] is not None]
    if len(pts) < 2:
        return
    plt = _plt()
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    plt.figure(figsize=(7, 5))
    plt.scatter(xs, ys, color="#c0392b", zorder=3)
    for x, y, name in pts:
        plt.annotate(name, (x, y), textcoords="offset points",
                     xytext=(5, 5), fontsize=8)
    # Linha de tendência (ajuste linear simples) quando há variação em x.
    if len(set(xs)) > 1:
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs)
        if denom:
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
            intercept = my - slope * mx
            xr = [min(xs), max(xs)]
            plt.plot(xr, [slope * x + intercept for x in xr],
                     "--", color="#7f8c8d", label="tendência")
            plt.legend()
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, filename)
    plt.savefig(out, dpi=130)
    plt.close()
    print("[OK] %s" % out)


def main():
    os.makedirs(PLOTS_DIR, exist_ok=True)
    summary = load_summary()
    if not summary:
        print("[ERRO] Nenhum resultado encontrado em %s. Rode os experimentos antes."
              % RESULTS_DIR)
        sys.exit(1)

    rows = [flatten(e) for e in summary]
    write_csv(rows)

    # Gráficos comparativos por cenário (normal vs adversos).
    bar_chart(rows, "startup_time_s", "Tempo de início (s)",
              "Tempo de início por cenário", "qoe_startup.png", "#2e86c1")
    bar_chart(rows, "rebuffer_time_s", "Tempo de rebuffering (s)",
              "Buffering por cenário", "qoe_rebuffer.png", "#e67e22")
    bar_chart(rows, "avg_bitrate_kbps", "Bitrate médio (kbps)",
              "Bitrate médio reproduzido por cenário", "qoe_bitrate.png", "#27ae60")

    # Correlação entre métricas de rede e QoE. Usa a vazão de DOWNLOAD medida
    # pelo próprio cliente (caminho servidor->cliente, que é o do streaming);
    # o iperf da coleta mede o uplink, não shapeado nos cenários de banda.
    scatter_chart(rows, "mean_throughput_mbps", "avg_bitrate_kbps",
                  "Vazão de download (Mbps)", "Bitrate médio (kbps)",
                  "Vazão de download x Bitrate reproduzido", "corr_throughput_bitrate.png")
    scatter_chart(rows, "loss_pct", "rebuffer_time_s",
                  "Perda de pacotes (%)", "Tempo de rebuffering (s)",
                  "Perda x Rebuffering", "corr_loss_rebuffer.png")
    scatter_chart(rows, "rtt_avg_ms", "startup_time_s",
                  "RTT médio (ms)", "Tempo de início (s)",
                  "Latência x Tempo de início", "corr_rtt_startup.png")

    print("\n[OK] Análise concluída. Gráficos em %s" % PLOTS_DIR)


if __name__ == "__main__":
    main()
