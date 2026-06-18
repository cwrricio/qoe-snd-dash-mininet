"""Testes do pipeline de análise: flatten, CSV e geração de gráficos."""

import csv
import json
import os

from experiments import analyze


SAMPLE = [
    {"scenario": "baseline", "description": "ref",
     "net": {"rtt_avg_ms": 0.5, "loss_pct": 0.0, "throughput_mbps": 95.0},
     "qoe": {"startup_time_s": 0.2, "rebuffer_events": 0, "rebuffer_time_s": 0.0,
             "avg_bitrate_kbps": 1500.0, "bitrate_switches": 1, "mean_throughput_mbps": 80.0}},
    {"scenario": "banda_baixa", "description": "3 Mbps",
     "net": {"rtt_avg_ms": 1.0, "loss_pct": 0.0, "throughput_mbps": 2.9},
     "qoe": {"startup_time_s": 1.8, "rebuffer_events": 3, "rebuffer_time_s": 6.4,
             "avg_bitrate_kbps": 300.0, "bitrate_switches": 0, "mean_throughput_mbps": 2.8}},
]


def test_flatten_merges_net_and_qoe():
    row = analyze.flatten(SAMPLE[1])
    assert row["scenario"] == "banda_baixa"
    assert row["throughput_mbps"] == 2.9
    assert row["avg_bitrate_kbps"] == 300.0
    assert row["rebuffer_events"] == 3


def test_flatten_handles_missing_sections():
    row = analyze.flatten({"scenario": "x"})
    assert row["scenario"] == "x"
    assert row["rtt_avg_ms"] is None
    assert row["startup_time_s"] is None


def test_load_summary_reads_summary_json(tmp_path, monkeypatch):
    results = tmp_path / "etapa2"
    results.mkdir()
    (results / "summary.json").write_text(json.dumps(SAMPLE))
    monkeypatch.setattr(analyze, "RESULTS_DIR", str(results))
    loaded = analyze.load_summary()
    assert [e["scenario"] for e in loaded] == ["baseline", "banda_baixa"]


def test_load_summary_rebuilds_from_qoe_dir(tmp_path, monkeypatch):
    results = tmp_path / "etapa2"
    qoe = results / "qoe"
    qoe.mkdir(parents=True)
    (qoe / "baseline.json").write_text(json.dumps(SAMPLE[0]["qoe"]))
    monkeypatch.setattr(analyze, "RESULTS_DIR", str(results))
    loaded = analyze.load_summary()
    assert loaded[0]["scenario"] == "baseline"
    assert loaded[0]["qoe"]["avg_bitrate_kbps"] == 1500.0


def test_write_csv_has_header_and_rows(tmp_path, monkeypatch):
    results = tmp_path / "etapa2"
    results.mkdir()
    monkeypatch.setattr(analyze, "RESULTS_DIR", str(results))
    rows = [analyze.flatten(e) for e in SAMPLE]
    analyze.write_csv(rows)
    path = results / "summary.csv"
    assert path.exists()
    with open(path) as f:
        data = list(csv.DictReader(f))
    assert len(data) == 2
    assert data[0]["scenario"] == "baseline"
    assert data[1]["avg_bitrate_kbps"] == "300.0"


def test_bar_chart_creates_png(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "PLOTS_DIR", str(tmp_path))
    rows = [analyze.flatten(e) for e in SAMPLE]
    analyze.bar_chart(rows, "avg_bitrate_kbps", "kbps", "Bitrate", "bitrate.png")
    assert os.path.exists(os.path.join(str(tmp_path), "bitrate.png"))


def test_scatter_chart_creates_png(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "PLOTS_DIR", str(tmp_path))
    rows = [analyze.flatten(e) for e in SAMPLE]
    analyze.scatter_chart(rows, "throughput_mbps", "avg_bitrate_kbps",
                          "Mbps", "kbps", "corr", "corr.png")
    assert os.path.exists(os.path.join(str(tmp_path), "corr.png"))
