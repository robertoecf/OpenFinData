"""CSV/ZIP parsing for CVM data. Semicolon-delimited, ISO-8859-1."""

from __future__ import annotations

import csv
import io
import re
import zipfile

from findata.http_client import get_bytes

_NON_DIGIT = re.compile(r"\D")


def cnpj_digits(value: str | None) -> str:
    """Strip a CNPJ to digits so punctuated and bare forms compare equal."""
    return _NON_DIGIT.sub("", value or "")


async def fetch_csv(url: str) -> list[dict[str, str]]:
    raw = await get_bytes(url)
    return list(csv.DictReader(io.StringIO(raw.decode("iso-8859-1")), delimiter=";"))


async def fetch_csv_from_zip(
    url: str,
    filename_contains: str | None = None,
) -> list[dict[str, str]]:
    raw = await get_bytes(url)
    results: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            if filename_contains and filename_contains not in name:
                continue
            with zf.open(name) as f:
                reader = csv.DictReader(
                    io.StringIO(f.read().decode("iso-8859-1")),
                    delimiter=";",
                )
                results.extend(reader)
    return results
