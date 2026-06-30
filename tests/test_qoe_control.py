"""Testes da logica pura de controle de QoE via SDN (Etapa 3)."""

from experiments.qoe_control import (
    link_utilization_mbps, is_congested, make_decision,
    format_decision_log, tc_priority_commands, tc_clear_command,
    ofctl_add_dash_flow, ofctl_del_dash_flow, DASH_PORT,
)
from experiments import analyze_etapa3


# ----- utilizacao do enlace -----

def test_utilization_basic():
    # 1.25 MB em 1 s = 10 Mbps.
    assert link_utilization_mbps(0, 1_250_000, 1.0) == 10.0


def test_utilization_uses_delta():
    assert link_utilization_mbps(1_250_000, 2_500_000, 1.0) == 10.0


def test_utilization_counter_reset_is_zero():
    assert link_utilization_mbps(5_000_000, 0, 1.0) == 0.0


def test_utilization_nonpositive_interval_is_zero():
    assert link_utilization_mbps(0, 1_000_000, 0) == 0.0


# ----- deteccao de congestionamento -----

def test_congested_above_threshold():
    assert is_congested(8.5, 10, threshold=0.8) is True


def test_not_congested_below_threshold():
    assert is_congested(7.9, 10, threshold=0.8) is False


def test_congested_exactly_at_threshold():
    assert is_congested(8.0, 10, threshold=0.8) is True


def test_zero_capacity_never_congested():
    assert is_congested(100, 0) is False


# ----- decisao -----

def test_decision_prioritizes_when_congested_and_mitigating():
    d = make_decision(9.0, 10, mitigate=True)
    assert d["congested"] is True
    assert d["action"] == "prioritize_dash"
    assert d["threshold_mbps"] == 8.0


def test_decision_monitors_when_not_congested():
    d = make_decision(3.0, 10, mitigate=True)
    assert d["congested"] is False
    assert d["action"] == "monitor"


def test_decision_baseline_never_acts_even_if_congested():
    d = make_decision(9.5, 10, mitigate=False)
    assert d["congested"] is True
    assert d["action"] == "monitor"


def test_format_decision_log_is_single_line_with_fields():
    d = make_decision(9.0, 10, mitigate=True)
    line = format_decision_log("2026-06-30 10:00:00", "s1", 2, d)
    assert "\n" not in line
    assert "action=prioritize_dash" in line
    assert "congested=True" in line
    assert "port=2" in line


# ----- comandos tc HTB -----

def test_tc_priority_starts_by_clearing():
    cmds = tc_priority_commands("h1-eth0", "10.0.0.2", 10, 8)
    assert cmds[0] == tc_clear_command("h1-eth0")


def test_tc_priority_creates_htb_with_two_classes():
    cmds = tc_priority_commands("h1-eth0", "10.0.0.2", 10, 8)
    joined = " ".join(cmds)
    assert "htb default 12" in joined
    assert "classid 1:11" in joined and "classid 1:12" in joined
    assert "rate 8mbit" in joined
    assert "rate 1mbit" in joined


def test_tc_priority_filter_matches_client_ip():
    cmds = tc_priority_commands("h1-eth0", "10.0.0.2", 10, 8)
    filter_cmd = [c for c in cmds if "filter" in c][0]
    assert "10.0.0.2/32" in filter_cmd
    assert "flowid 1:11" in filter_cmd


def test_tc_clear_is_idempotent():
    assert "2>/dev/null" in tc_clear_command("h1-eth0")


# ----- comandos OpenFlow (ovs-ofctl) -----

def test_ofctl_add_contains_priority_and_port():
    cmd = ofctl_add_dash_flow("s1")
    assert "priority=200" in cmd
    assert ("tp_src=%d" % DASH_PORT) in cmd
    assert "actions=normal" in cmd


def test_ofctl_del_matches_same_flow():
    add = ofctl_add_dash_flow("s1")
    del_ = ofctl_del_dash_flow("s1")
    assert "add-flow" in add
    assert "del-flows" in del_
    assert ("tp_src=%d" % DASH_PORT) in del_


# ----- analise (ganho percentual) -----

def test_improvement_percent_change():
    rows = [
        {"mode": "sem_controle", "rebuffer_time_s": 10.0, "avg_bitrate_kbps": 500},
        {"mode": "com_controle", "rebuffer_time_s": 2.0,  "avg_bitrate_kbps": 750},
    ]
    assert analyze_etapa3.improvement(rows, "rebuffer_time_s") == -80.0
    assert analyze_etapa3.improvement(rows, "avg_bitrate_kbps") == 50.0


def test_improvement_none_when_missing_or_zero_base():
    rows = [
        {"mode": "sem_controle", "rebuffer_time_s": 0.0},
        {"mode": "com_controle", "rebuffer_time_s": 2.0},
    ]
    assert analyze_etapa3.improvement(rows, "rebuffer_time_s") is None
    assert analyze_etapa3.improvement([], "rebuffer_time_s") is None


def test_flatten_handles_missing_sections():
    flat = analyze_etapa3.flatten({"mode": "com_controle"})
    assert flat["mode"] == "com_controle"
    assert flat["rebuffer_time_s"] is None
