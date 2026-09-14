"""
Tests para stop_gate_mcp.py — Stop hook de mcp_smart_context.
Cubre el control de flujo SIN correr el oracle real.
"""
import io
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))

import stop_gate_mcp
from stop_gate_mcp import main


def _fake_stdin(payload: bytes):
    return type("FakeStdin", (), {"buffer": io.BytesIO(payload)})()


# ---------------------------------------------------------------------------
# stop_hook_active → salida inmediata sin oracle
# ---------------------------------------------------------------------------

def test_stop_hook_active_exits_without_oracle(monkeypatch):
    payload = json.dumps({"stop_hook_active": True}).encode()
    monkeypatch.setattr(sys, "stdin", _fake_stdin(payload))
    monkeypatch.delenv("RALPH_ACTIVE", raising=False)
    mock_run = MagicMock()
    monkeypatch.setattr(stop_gate_mcp.subprocess, "run", mock_run)

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# RALPH_ACTIVE=1 → salida inmediata sin oracle
# ---------------------------------------------------------------------------

def test_ralph_active_exits_without_oracle(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _fake_stdin(b"{}"))
    monkeypatch.setenv("RALPH_ACTIVE", "1")
    mock_run = MagicMock()
    monkeypatch.setattr(stop_gate_mcp.subprocess, "run", mock_run)

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Oracle returncode==0 → ITER_FILE eliminado (no crece el contador)
# ---------------------------------------------------------------------------

def test_oracle_success_unlinks_iter_file(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdin", _fake_stdin(b"{}"))
    monkeypatch.delenv("RALPH_ACTIVE", raising=False)

    iter_file = tmp_path / "iter"
    monkeypatch.setattr(stop_gate_mcp, "ITER_FILE", iter_file)

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = "Oracle OK MRR=0.958"
    fake_result.stderr = ""
    monkeypatch.setattr(stop_gate_mcp.subprocess, "run", lambda *a, **k: fake_result)

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert not iter_file.exists()


def test_oracle_success_counter_does_not_accumulate(monkeypatch, tmp_path):
    """Dos calls con gate verde → ITER_FILE no queda con contador creciente."""
    monkeypatch.delenv("RALPH_ACTIVE", raising=False)

    iter_file = tmp_path / "iter"
    monkeypatch.setattr(stop_gate_mcp, "ITER_FILE", iter_file)

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = ""
    fake_result.stderr = ""
    monkeypatch.setattr(stop_gate_mcp.subprocess, "run", lambda *a, **k: fake_result)

    for _ in range(2):
        monkeypatch.setattr(sys, "stdin", _fake_stdin(b"{}"))
        with pytest.raises(SystemExit):
            main()

    assert not iter_file.exists()


# ---------------------------------------------------------------------------
# Oracle returncode!=0 → bloquea (decision=block en stdout)
# ---------------------------------------------------------------------------

def test_oracle_failure_outputs_block_decision(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "stdin", _fake_stdin(b"{}"))
    monkeypatch.delenv("RALPH_ACTIVE", raising=False)

    iter_file = tmp_path / "iter"
    monkeypatch.setattr(stop_gate_mcp, "ITER_FILE", iter_file)

    fake_result = MagicMock()
    fake_result.returncode = 1
    fake_result.stdout = ""
    fake_result.stderr = ""
    monkeypatch.setattr(stop_gate_mcp.subprocess, "run", lambda *a, **k: fake_result)

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out.strip()
    block = json.loads(out)
    assert block["decision"] == "block"
