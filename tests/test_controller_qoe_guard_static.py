"""Verificacoes estaticas do controlador POX da Etapa 3."""

import ast
from pathlib import Path

from experiments import qoe_control


def test_pox_controller_only_references_existing_qoe_control_symbols():
    source = Path("controller/qoe_guard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    referenced = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "qoe_control"
    }

    missing = sorted(name for name in referenced if not hasattr(qoe_control, name))
    assert missing == []
