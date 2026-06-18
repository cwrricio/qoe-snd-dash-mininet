"""Testes das funções puras de degradação de rede e parsing (netimpair)."""

import os

from experiments.netimpair import (
    build_tc_commands, clear_tc_command, parse_ping, parse_iperf,
    restore_ownership,
)


def test_clear_command():
    assert clear_tc_command("h1-eth0") == "tc qdisc del dev h1-eth0 root 2>/dev/null"


def test_no_params_only_clears():
    cmds = build_tc_commands("h1-eth0")
    assert cmds == [clear_tc_command("h1-eth0")]


def test_bandwidth_only_uses_tbf_as_root():
    cmds = build_tc_commands("h1-eth0", bw=3)
    assert cmds[0].startswith("tc qdisc del")
    assert "root handle 1: tbf rate 3mbit" in cmds[1]
    assert "netem" not in " ".join(cmds)


def test_delay_only_uses_netem():
    cmds = build_tc_commands("h1-eth0", delay="150ms")
    assert "root handle 1: netem delay 150ms" in cmds[1]
    assert "tbf" not in " ".join(cmds)


def test_delay_with_jitter():
    cmds = build_tc_commands("h1-eth0", delay="50ms", jitter="30ms")
    assert "delay 50ms 30ms distribution normal" in cmds[1]


def test_jitter_without_delay_defaults_delay_zero():
    cmds = build_tc_commands("h1-eth0", jitter="20ms")
    assert "delay 0ms 20ms distribution normal" in cmds[1]


def test_loss_only():
    cmds = build_tc_commands("h1-eth0", loss=5)
    assert "netem loss 5%" in cmds[1]


def test_combined_netem_root_plus_tbf_child():
    cmds = build_tc_commands("h1-eth0", bw=3, delay="100ms", loss=2)
    joined = "\n".join(cmds)
    assert "root handle 1: netem delay 100ms loss 2%" in joined
    assert "parent 1: handle 2: tbf rate 3mbit" in joined
    # ordem: limpar -> netem -> tbf
    assert cmds[0].startswith("tc qdisc del")
    assert "netem" in cmds[1]
    assert "tbf" in cmds[2]


def test_parse_ping_with_loss_and_rtt():
    out = ("10 packets transmitted, 9 received, 10% packet loss, time 9013ms\n"
           "rtt min/avg/max/mdev = 50.123/152.456/260.789/40.111 ms")
    rtt, loss = parse_ping(out)
    assert rtt == 152.456
    assert loss == 10.0


def test_parse_ping_zero_loss():
    out = ("10 packets transmitted, 10 received, 0% packet loss, time 100ms\n"
           "rtt min/avg/max/mdev = 0.030/0.045/0.060/0.010 ms")
    rtt, loss = parse_ping(out)
    assert loss == 0.0
    assert rtt == 0.045


def test_parse_ping_missing_returns_none():
    rtt, loss = parse_ping("nada aqui")
    assert rtt is None and loss is None


def test_parse_iperf_mbits():
    out = "[  3]  0.0-5.0 sec  1.75 MBytes  2.93 Mbits/sec"
    assert parse_iperf(out) == 2.93


def test_parse_iperf_kbits_converted_to_mbits():
    out = "[  3]  0.0-5.0 sec  500 KBytes  800 Kbits/sec"
    assert parse_iperf(out) == 0.8


def test_parse_iperf_gbits_converted_to_mbits():
    out = "[  3]  0.0-5.0 sec  5 GBytes  1.5 Gbits/sec"
    assert parse_iperf(out) == 1500.0


def test_parse_iperf_missing_returns_none():
    assert parse_iperf("sem vazao") is None


def test_restore_ownership_noop_without_sudo_env(tmp_path, monkeypatch):
    monkeypatch.delenv("SUDO_UID", raising=False)
    monkeypatch.delenv("SUDO_GID", raising=False)
    f = tmp_path / "a.txt"
    f.write_text("x")
    restore_ownership(str(tmp_path))  # não deve levantar
    assert f.exists()


def test_restore_ownership_chowns_to_current_uid(tmp_path, monkeypatch):
    # Define SUDO_UID/GID como o usuário atual: chown é no-op, mas exercita
    # o caminho de percorrer e chamar os.chown sem precisar de root.
    monkeypatch.setenv("SUDO_UID", str(os.getuid()))
    monkeypatch.setenv("SUDO_GID", str(os.getgid()))
    sub = tmp_path / "etapa2" / "qoe"
    sub.mkdir(parents=True)
    (sub / "baseline.json").write_text("{}")
    restore_ownership(str(tmp_path))
    assert os.stat(sub / "baseline.json").st_uid == os.getuid()


def test_restore_ownership_missing_path_is_safe(monkeypatch):
    monkeypatch.setenv("SUDO_UID", "0")
    monkeypatch.setenv("SUDO_GID", "0")
    restore_ownership("/caminho/que/nao/existe")  # não deve levantar
