"""CLI smoke tests with network access mocked."""

from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from findata import __version__
from findata.cli import app

runner = CliRunner()


def test_help_exits_successfully() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "bcb" in result.stdout


def test_bcb_series_prints_catalog() -> None:
    result = runner.invoke(app, ["bcb", "series"])

    assert result.exit_code == 0
    assert "BCB Series Catalog" in result.stdout
    assert "selic" in result.stdout


def test_version_exits_successfully() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


@respx.mock
def test_bcb_get_uses_mocked_api() -> None:
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1"
    respx.get(url, params={"formato": "json"}).mock(
        return_value=httpx.Response(
            200,
            json=[{"data": "30/07/2026", "valor": "15.0000"}],
        )
    )

    result = runner.invoke(app, ["bcb", "get", "selic", "--last", "1"])

    assert result.exit_code == 0
    assert "BCB: selic" in result.stdout
    assert "30/07/2026" in result.stdout
    assert "15.0000" in result.stdout
