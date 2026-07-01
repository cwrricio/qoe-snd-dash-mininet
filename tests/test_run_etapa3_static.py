"""Verificacoes estaticas do orquestrador reproduzivel da Etapa 3."""

import ast
from pathlib import Path


def _tree():
    return ast.parse(Path("experiments/run_etapa3.py").read_text(encoding="utf-8"))


def test_etapa3_defaults_to_pox_controller():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "default" and isinstance(keyword.value, ast.Constant):
                    if keyword.value.value == "pox":
                        return
    raise AssertionError("run_etapa3.py deve usar controller='pox' por padrao")


def test_etapa3_uses_remote_controller_for_pox_mode():
    source = Path("experiments/run_etapa3.py").read_text(encoding="utf-8")
    assert "PoxControllerProcess" in source
    assert "RemoteController" in source
    assert "controller == \"pox\"" in source
