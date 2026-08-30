"""CVM open-fund cadastral data (Resolução 175 registro fundo/classe/subclasse).

``cad_fi.csv`` only lists funds *not* adapted to RCVM 175. Active open-ended
funds (including previdência FI/FIF) live in
``registro_fundo_classe.zip`` — fundo + classe + subclasse, updated Tue–Sat.

https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Callable
from typing import NamedTuple

from pydantic import BaseModel

from findata._cache import TTLCache
from findata.http_client import get_bytes
from findata.sources.cvm.parser import cnpj_digits

REGISTRO_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
_MIN_NAME_QUERY = 2


class FundSubclass(BaseModel):
    id_subclasse: str
    codigo_cvm: str
    nome: str
    situacao: str
    forma_condominio: str
    exclusivo: str
    publico_alvo: str
    previdenciario: str
    exclusivo_previdencia_complementar: str


class FundClasse(BaseModel):
    id_registro_classe: str
    cnpj_classe: str
    codigo_cvm: str
    nome: str
    tipo_classe: str
    situacao: str
    classificacao: str
    classe_anbima: str
    forma_condominio: str
    exclusivo: str
    publico_alvo: str
    patrimonio_liquido: float | None = None
    data_patrimonio_liquido: str = ""
    auditor: str = ""
    custodiante: str = ""
    subclasses: list[FundSubclass] = []


class FundCadastro(BaseModel):
    source: str = "cvm_registro_fundo_classe"
    cnpj: str
    codigo_cvm: str
    nome: str
    tipo: str
    situacao: str
    data_registro: str
    data_constituicao: str
    data_adaptacao_rcvm175: str
    patrimonio_liquido: float | None = None
    data_patrimonio_liquido: str = ""
    gestor: str = ""
    cnpj_gestor: str = ""
    administrador: str = ""
    cnpj_administrador: str = ""
    diretor: str = ""
    classes: list[FundClasse] = []


class _RegistroTables(NamedTuple):
    fundos: list[dict[str, str]]
    classes: list[dict[str, str]]
    subclasses: list[dict[str, str]]


_registro_cache: TTLCache[_RegistroTables] = TTLCache(ttl=3600)


def _opt_float(value: str) -> float | None:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _read_zip_csvs(raw: bytes) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            with zf.open(name) as handle:
                text = handle.read().decode("iso-8859-1")
            out[name] = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    return out


async def _load_registro() -> _RegistroTables:
    files = _read_zip_csvs(await get_bytes(REGISTRO_URL))
    fundos = files.get("registro_fundo.csv") or []
    classes = files.get("registro_classe.csv") or []
    subclasses = files.get("registro_subclasse.csv") or []
    return _RegistroTables(fundos, classes, subclasses)


def _parse_subclass(row: dict[str, str]) -> FundSubclass:
    return FundSubclass(
        id_subclasse=row.get("ID_Subclasse", ""),
        codigo_cvm=row.get("Codigo_CVM", ""),
        nome=row.get("Denominacao_Social", ""),
        situacao=row.get("Situacao", ""),
        forma_condominio=row.get("Forma_Condominio", ""),
        exclusivo=row.get("Exclusivo", ""),
        publico_alvo=row.get("Publico_Alvo", ""),
        previdenciario=row.get("Previdenciario", ""),
        exclusivo_previdencia_complementar=row.get("Exclusivo_Previdencia_Complementar", ""),
    )


def _parse_classe(row: dict[str, str], subclasses: list[FundSubclass]) -> FundClasse:
    return FundClasse(
        id_registro_classe=row.get("ID_Registro_Classe", ""),
        cnpj_classe=row.get("CNPJ_Classe", ""),
        codigo_cvm=row.get("Codigo_CVM", ""),
        nome=row.get("Denominacao_Social", ""),
        tipo_classe=row.get("Tipo_Classe", ""),
        situacao=row.get("Situacao", ""),
        classificacao=row.get("Classificacao", ""),
        classe_anbima=row.get("Classificacao_Anbima", ""),
        forma_condominio=row.get("Forma_Condominio", ""),
        exclusivo=row.get("Exclusivo", ""),
        publico_alvo=row.get("Publico_Alvo", ""),
        patrimonio_liquido=_opt_float(row.get("Patrimonio_Liquido", "")),
        data_patrimonio_liquido=row.get("Data_Patrimonio_Liquido", ""),
        auditor=row.get("Auditor", ""),
        custodiante=row.get("Custodiante", ""),
        subclasses=subclasses,
    )


def _parse_fundo(row: dict[str, str], classes: list[FundClasse]) -> FundCadastro:
    return FundCadastro(
        cnpj=row.get("CNPJ_Fundo", ""),
        codigo_cvm=row.get("Codigo_CVM", ""),
        nome=row.get("Denominacao_Social", ""),
        tipo=row.get("Tipo_Fundo", ""),
        situacao=row.get("Situacao", ""),
        data_registro=row.get("Data_Registro", ""),
        data_constituicao=row.get("Data_Constituicao", ""),
        data_adaptacao_rcvm175=row.get("Data_Adaptacao_RCVM175", ""),
        patrimonio_liquido=_opt_float(row.get("Patrimonio_Liquido", "")),
        data_patrimonio_liquido=row.get("Data_Patrimonio_Liquido", ""),
        gestor=row.get("Gestor", ""),
        cnpj_gestor=row.get("CPF_CNPJ_Gestor", ""),
        administrador=row.get("Administrador", ""),
        cnpj_administrador=row.get("CNPJ_Administrador", ""),
        diretor=row.get("Diretor", ""),
        classes=classes,
    )


def _row_matches(
    row: dict[str, str],
    *,
    cnpj_fields: tuple[str, ...],
    name_fields: tuple[str, ...],
    needle_digits: str,
    needle_name: str,
) -> bool:
    if needle_digits:
        return any(cnpj_digits(row.get(field)) == needle_digits for field in cnpj_fields)
    return any(needle_name in (row.get(field) or "").casefold() for field in name_fields)


def _take(
    rows: list[dict[str, str]], pred: Callable[[dict[str, str]], bool], limit: int
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in rows:
        if pred(row):
            selected.append(row)
            if len(selected) >= limit:
                break
    return selected


def _select_fundos(
    tables: _RegistroTables, needle_digits: str, needle_name: str, limit: int
) -> list[dict[str, str]]:
    selected = _take(
        tables.fundos,
        lambda row: _row_matches(
            row,
            cnpj_fields=("CNPJ_Fundo",),
            name_fields=("Denominacao_Social",),
            needle_digits=needle_digits,
            needle_name=needle_name,
        ),
        limit,
    )
    if needle_digits:
        if selected:
            return selected
        class_ids = {
            row.get("ID_Registro_Fundo", "")
            for row in tables.classes
            if cnpj_digits(row.get("CNPJ_Classe")) == needle_digits
        }
        return _take(tables.fundos, lambda row: row.get("ID_Registro_Fundo") in class_ids, limit)
    extra_fundo_ids = {
        row.get("ID_Registro_Fundo", "")
        for row in tables.classes
        if needle_name in (row.get("Denominacao_Social") or "").casefold()
    }
    sub_class_ids = {
        row.get("ID_Registro_Classe", "")
        for row in tables.subclasses
        if needle_name in (row.get("Denominacao_Social") or "").casefold()
    }
    if sub_class_ids:
        extra_fundo_ids.update(
            row.get("ID_Registro_Fundo", "")
            for row in tables.classes
            if row.get("ID_Registro_Classe") in sub_class_ids
        )
    already = {row.get("ID_Registro_Fundo") for row in selected}
    for row in tables.fundos:
        fundo_id = row.get("ID_Registro_Fundo")
        if fundo_id in extra_fundo_ids and fundo_id not in already:
            selected.append(row)
            already.add(fundo_id)
            if len(selected) >= limit:
                break
    return selected


def _assemble(tables: _RegistroTables, selected: list[dict[str, str]]) -> list[FundCadastro]:
    keep_ids = {row.get("ID_Registro_Fundo", "") for row in selected}
    classes_by_fundo: dict[str, list[dict[str, str]]] = {}
    for row in tables.classes:
        fundo_id = row.get("ID_Registro_Fundo", "")
        if fundo_id in keep_ids:
            classes_by_fundo.setdefault(fundo_id, []).append(row)
    classe_ids = {
        row.get("ID_Registro_Classe", "") for rows in classes_by_fundo.values() for row in rows
    }
    subclasses_by_classe: dict[str, list[FundSubclass]] = {}
    for row in tables.subclasses:
        classe_id = row.get("ID_Registro_Classe", "")
        if classe_id in classe_ids:
            subclasses_by_classe.setdefault(classe_id, []).append(_parse_subclass(row))
    result: list[FundCadastro] = []
    for fundo in selected:
        fundo_id = fundo.get("ID_Registro_Fundo", "")
        parsed_classes = [
            _parse_classe(row, subclasses_by_classe.get(row.get("ID_Registro_Classe", ""), []))
            for row in classes_by_fundo.get(fundo_id, [])
        ]
        result.append(_parse_fundo(fundo, parsed_classes))
    return result


def related_quote_cnpjs(funds: list[FundCadastro], requested_digits: str) -> list[str]:
    """INF_DIARIO CNPJs to scan for one catalog hit.

    A single-class RCVM 175 adaptation may add the sibling fundo/classe CNPJ so
    legacy 555 rows stitch onto the continuation class. Multi-class funds never
    borrow another class — those series are different investments.
    """
    requested = cnpj_digits(requested_digits)
    out: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        digits = cnpj_digits(raw)
        if digits and digits not in seen:
            seen.add(digits)
            out.append(digits)

    add(requested)
    for fund in funds:
        fund_digits = cnpj_digits(fund.cnpj)
        class_digits = list(
            dict.fromkeys(
                cnpj_digits(classe.cnpj_classe)
                for classe in fund.classes
                if cnpj_digits(classe.cnpj_classe)
            )
        )
        matched_fund = fund_digits == requested
        matched_class = any(cnpj_digits(classe.cnpj_classe) == requested for classe in fund.classes)
        if matched_fund:
            for digits in class_digits:
                add(digits)
        elif matched_class and len(class_digits) == 1:
            add(fund_digits)
    return out


def continuation_class_cnpj(funds: list[FundCadastro], requested_digits: str) -> str | None:
    """Canonical class CNPJ for a single-class 555→175 stitch, else None."""
    requested = cnpj_digits(requested_digits)
    for fund in funds:
        class_digits = list(
            dict.fromkeys(
                cnpj_digits(classe.cnpj_classe)
                for classe in fund.classes
                if cnpj_digits(classe.cnpj_classe)
            )
        )
        matched = requested == cnpj_digits(fund.cnpj) or requested in class_digits
        if matched and len(class_digits) == 1:
            return class_digits[0]
    return None


def quote_served_label(funds: list[FundCadastro], cnpj: str, id_subclasse: str) -> dict[str, str]:
    """Nicename / CVM / ANBIMA class for the series actually returned."""
    digits = cnpj_digits(cnpj)
    nicename = ""
    tipo_classe = ""
    classificacao = ""
    classe_anbima = ""
    subclass_name = ""
    for fund in funds:
        if cnpj_digits(fund.cnpj) == digits and not nicename:
            nicename = fund.nome
        for classe in fund.classes:
            if cnpj_digits(classe.cnpj_classe) != digits:
                continue
            nicename = classe.nome or nicename
            tipo_classe = classe.tipo_classe
            classificacao = classe.classificacao
            classe_anbima = classe.classe_anbima
            for sub in classe.subclasses:
                if id_subclasse and sub.id_subclasse == id_subclasse:
                    subclass_name = sub.nome
                    if sub.nome:
                        nicename = sub.nome
    return {
        "nicename": nicename,
        "tipo_classe": tipo_classe,
        "classificacao": classificacao,
        "classe_anbima": classe_anbima,
        "subclass_name": subclass_name,
    }


async def get_fund_cadastro(
    cnpj: str | None = None,
    q: str | None = None,
    limit: int = 20,
) -> list[FundCadastro]:
    """Look up an open-ended fund in the official RCVM 175 cadastral zip.

    Requires ``cnpj`` (punctuated or digits) or a name fragment ``q``.
    Does not dump the full universe.
    """
    needle_digits = cnpj_digits(cnpj)
    needle_name = (q or "").strip().casefold()
    if not needle_digits and len(needle_name) < _MIN_NAME_QUERY:
        raise ValueError("cadastro requires `cnpj` or `q` (min 2 chars)")
    tables = await _registro_cache.get_or_load(_load_registro)
    selected = _select_fundos(tables, needle_digits, needle_name, limit)
    return _assemble(tables, selected) if selected else []
