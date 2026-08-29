import { errorResult, getBytes, jsonResult } from "../lib/http.ts";
import { cnpjDigits, optFloat, scanCsv, scanCsvForNeedles, zipFile } from "../lib/zipCsv.ts";

const REGISTRO_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip";
const DAILY_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ym}.zip";

const CVM_TIMEOUT_MS = 45_000;
const CVM_MAX_BYTES = 16_000_000;
const CATALOG_SCAN_CAP = 200;
const DAILY_SCAN_CAP = 2_000;

async function fetchCvmZip(url: string): Promise<Uint8Array> {
  return getBytes(url, { maxBytes: CVM_MAX_BYTES, timeoutMs: CVM_TIMEOUT_MS });
}

function maskCnpj(digits: string): string {
  if (digits.length !== 14) {
    return digits;
  }
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
}

function cnpjNeedles(digits: string): string[] {
  return digits.length === 14 ? [digits, maskCnpj(digits)] : [digits];
}

function mapFundo(row: Record<string, string>, classes: Record<string, unknown>[]) {
  return {
    source: "cvm_registro_fundo_classe",
    cnpj: row.CNPJ_Fundo ?? "",
    codigo_cvm: row.Codigo_CVM ?? "",
    nome: row.Denominacao_Social ?? "",
    tipo: row.Tipo_Fundo ?? "",
    situacao: row.Situacao ?? "",
    data_registro: row.Data_Registro ?? "",
    data_constituicao: row.Data_Constituicao ?? "",
    data_adaptacao_rcvm175: row.Data_Adaptacao_RCVM175 ?? "",
    patrimonio_liquido: optFloat(row.Patrimonio_Liquido),
    data_patrimonio_liquido: row.Data_Patrimonio_Liquido ?? "",
    gestor: row.Gestor ?? "",
    cnpj_gestor: row.CPF_CNPJ_Gestor ?? "",
    administrador: row.Administrador ?? "",
    cnpj_administrador: row.CNPJ_Administrador ?? "",
    diretor: row.Diretor ?? "",
    classes,
  };
}

function mapClasse(row: Record<string, string>, subclasses: Record<string, unknown>[]) {
  return {
    id_registro_classe: row.ID_Registro_Classe ?? "",
    cnpj_classe: row.CNPJ_Classe ?? "",
    codigo_cvm: row.Codigo_CVM ?? "",
    nome: row.Denominacao_Social ?? "",
    tipo_classe: row.Tipo_Classe ?? "",
    situacao: row.Situacao ?? "",
    classificacao: row.Classificacao ?? "",
    classe_anbima: row.Classificacao_Anbima ?? "",
    forma_condominio: row.Forma_Condominio ?? "",
    exclusivo: row.Exclusivo ?? "",
    publico_alvo: row.Publico_Alvo ?? "",
    patrimonio_liquido: optFloat(row.Patrimonio_Liquido),
    data_patrimonio_liquido: row.Data_Patrimonio_Liquido ?? "",
    auditor: row.Auditor ?? "",
    custodiante: row.Custodiante ?? "",
    subclasses,
  };
}

function mapSubclass(row: Record<string, string>) {
  return {
    id_subclasse: row.ID_Subclasse ?? "",
    codigo_cvm: row.Codigo_CVM ?? "",
    nome: row.Denominacao_Social ?? "",
    situacao: row.Situacao ?? "",
    forma_condominio: row.Forma_Condominio ?? "",
    exclusivo: row.Exclusivo ?? "",
    publico_alvo: row.Publico_Alvo ?? "",
    previdenciario: row.Previdenciario ?? "",
    exclusivo_previdencia_complementar: row.Exclusivo_Previdencia_Complementar ?? "",
  };
}

async function catalogByCnpj(zip: Uint8Array, digits: string, limit: number) {
  const needles = cnpjNeedles(digits);
  const fundosByCnpj = scanCsvForNeedles(await zipFile(zip, "registro_fundo.csv"), needles, limit);
  const classesByCnpj = scanCsvForNeedles(
    await zipFile(zip, "registro_classe.csv"),
    needles,
    CATALOG_SCAN_CAP,
  );
  const keepIds = new Set(fundosByCnpj.map((row) => row.ID_Registro_Fundo ?? ""));
  for (const row of classesByCnpj) {
    keepIds.add(row.ID_Registro_Fundo ?? "");
  }
  const fundos =
    fundosByCnpj.length > 0
      ? fundosByCnpj
      : scanCsv(
          await zipFile(zip, "registro_fundo.csv"),
          (row) => keepIds.has(row.ID_Registro_Fundo ?? ""),
          limit,
        );
  const classes = scanCsv(
    await zipFile(zip, "registro_classe.csv"),
    (row) => keepIds.has(row.ID_Registro_Fundo ?? ""),
    CATALOG_SCAN_CAP,
  );
  const classIds = new Set(classes.map((row) => row.ID_Registro_Classe ?? ""));
  const subclasses = scanCsv(
    await zipFile(zip, "registro_subclasse.csv"),
    (row) => classIds.has(row.ID_Registro_Classe ?? ""),
    CATALOG_SCAN_CAP,
  );
  const subclassesByClasse = new Map<string, Record<string, unknown>[]>();
  for (const row of subclasses) {
    const key = row.ID_Registro_Classe ?? "";
    const list = subclassesByClasse.get(key) ?? [];
    list.push(mapSubclass(row));
    subclassesByClasse.set(key, list);
  }
  const classesByFundo = new Map<string, Record<string, unknown>[]>();
  for (const row of classes) {
    const key = row.ID_Registro_Fundo ?? "";
    const list = classesByFundo.get(key) ?? [];
    list.push(mapClasse(row, subclassesByClasse.get(row.ID_Registro_Classe ?? "") ?? []));
    classesByFundo.set(key, list);
  }
  return fundos.slice(0, limit).map((row) => mapFundo(row, classesByFundo.get(row.ID_Registro_Fundo ?? "") ?? []));
}

async function catalogByName(zip: Uint8Array, q: string, limit: number) {
  const needle = q.toLowerCase();
  const fundos = scanCsv(
    await zipFile(zip, "registro_fundo.csv"),
    (row) => (row.Denominacao_Social ?? "").toLowerCase().includes(needle),
    limit,
  );
  if (fundos.length === 0) {
    return [];
  }
  const fundoIds = new Set(fundos.map((row) => row.ID_Registro_Fundo ?? ""));
  const classes = scanCsv(
    await zipFile(zip, "registro_classe.csv"),
    (row) => fundoIds.has(row.ID_Registro_Fundo ?? ""),
    CATALOG_SCAN_CAP,
  );
  const classIds = new Set(classes.map((row) => row.ID_Registro_Classe ?? ""));
  const subclasses = scanCsv(
    await zipFile(zip, "registro_subclasse.csv"),
    (row) => classIds.has(row.ID_Registro_Classe ?? ""),
    CATALOG_SCAN_CAP,
  );
  const subclassesByClasse = new Map<string, Record<string, unknown>[]>();
  for (const row of subclasses) {
    const key = row.ID_Registro_Classe ?? "";
    const list = subclassesByClasse.get(key) ?? [];
    list.push(mapSubclass(row));
    subclassesByClasse.set(key, list);
  }
  const classesByFundo = new Map<string, Record<string, unknown>[]>();
  for (const row of classes) {
    const key = row.ID_Registro_Fundo ?? "";
    const list = classesByFundo.get(key) ?? [];
    list.push(mapClasse(row, subclassesByClasse.get(row.ID_Registro_Classe ?? "") ?? []));
    classesByFundo.set(key, list);
  }
  return fundos.map((row) => mapFundo(row, classesByFundo.get(row.ID_Registro_Fundo ?? "") ?? []));
}

function currentYearMonth(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getUTCFullYear(), month: now.getUTCMonth() + 1 };
}

function mapDaily(row: Record<string, string>) {
  return {
    cnpj: row.CNPJ_FUNDO_CLASSE || row.CNPJ_FUNDO || "",
    dt_comptc: row.DT_COMPTC ?? "",
    vl_total: Number(row.VL_TOTAL || 0),
    vl_quota: Number(row.VL_QUOTA || 0),
    vl_patrimonio_liq: Number(row.VL_PATRIM_LIQ || 0),
    captacao_dia: Number(row.CAPTC_DIA || 0),
    resgate_dia: Number(row.RESG_DIA || 0),
    nr_cotistas: Number(row.NR_COTST || 0),
    tp_fundo_classe: row.TP_FUNDO_CLASSE ?? "",
    id_subclasse: row.ID_SUBCLASSE ?? "",
  };
}

export async function cvmFund(args: {
  dataset?: "catalog" | "daily";
  cnpj?: string;
  q?: string;
  year?: number;
  month?: number;
  limit?: number;
}) {
  const dataset = args.dataset ?? "catalog";
  const limit = Math.min(args.limit ?? (dataset === "daily" ? 500 : 20), dataset === "daily" ? 2000 : 100);
  if (dataset === "catalog") {
    const digits = cnpjDigits(args.cnpj);
    const q = args.q?.trim() ?? "";
    if (!digits && q.length < 2) {
      return errorResult("dataset=catalog requires `cnpj` or `q` (min 2 chars)");
    }
    const zip = await fetchCvmZip(REGISTRO_URL);
    const rows = digits
      ? await catalogByCnpj(zip, digits, limit)
      : await catalogByName(zip, q, limit);
    return jsonResult(rows);
  }
  const digits = cnpjDigits(args.cnpj);
  if (digits.length < 8) {
    return errorResult("dataset=daily requires `cnpj`");
  }
  const fallback = currentYearMonth();
  const year = args.year ?? fallback.year;
  const month = args.month ?? fallback.month;
  if (year < 2021 || month < 1 || month > 12) {
    return errorResult("dataset=daily requires year>=2021 and month 1-12");
  }
  const ym = `${year}${String(month).padStart(2, "0")}`;
  const zip = await fetchCvmZip(DAILY_URL.replace("{ym}", ym));
  const csvName = `inf_diario_fi_${ym}.csv`;
  const rows = scanCsvForNeedles(await zipFile(zip, csvName), cnpjNeedles(digits), Math.min(limit, DAILY_SCAN_CAP));
  return jsonResult({
    source: "cvm_inf_diario",
    year,
    month,
    cnpj: digits,
    note: "CDA carteira is a separate delayed monthly feed and is not included.",
    series: rows.map(mapDaily),
  });
}
