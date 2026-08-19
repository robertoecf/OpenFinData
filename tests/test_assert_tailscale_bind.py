"""TAILSCALE_IP must be a Tailscale CGNAT address, not a wildcard bind."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "deploy" / "assert_tailscale_bind.py"


def _bind_mod():
    spec = importlib.util.spec_from_file_location("assert_tailscale_bind", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_allows_tailscale_cgnat() -> None:
    allowed = _bind_mod().allowed_tailscale_bind
    assert allowed("100.90.45.18") is True
    assert allowed("100.64.0.1") is True


@pytest.mark.parametrize("raw", ["0.0.0.0", "127.0.0.1", "8.8.8.8", "192.168.0.1", "not-an-ip", ""])
def test_rejects_non_tailscale_binds(raw: str) -> None:
    assert _bind_mod().allowed_tailscale_bind(raw) is False


def test_script_exits_nonzero_for_wildcard() -> None:
    env = os.environ.copy()
    env["TAILSCALE_IP"] = "0.0.0.0"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "0.0.0.0" in result.stderr
