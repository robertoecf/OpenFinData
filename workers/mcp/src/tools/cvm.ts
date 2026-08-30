import { errorResult, getBytes, jsonResult, UpstreamError } from "../lib/http.ts";
import {
  cnpjDigits,
  listZipEntryNames,
  optFloat,
  scanZipCsv,
  scanZipCsvForNeedles,
} from "../lib/zipCsv.ts";

const REGISTRO_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip";
const DAILY_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ym}.zip";
const CDA_URL = "https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{ym}.zip";
const CDA_LISTING_URL = "https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/";
const DAILY_LISTING_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/";

const CVM_TIMEOUT_MS = 45_000;
const CVM_MAX_BYTES = 32_000_000;
const CVM_LISTING_MAX_BYTES = 2_000_000;
const CATALOG_CLASS_CAP = 2_000;
const DAILY_SCAN_CAP = 2_000;
const HOLDINGS_SCAN_CAP = 5_000;
const DAILY_MONTHS_MAX = 3;

export type CvmDataset = "catalog" | "daily" | "holdings" | "periods";
export type CvmPeriodProduct = "CDA" | "INF_DIARIO";

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

function fieldCnpjEquals(
  row: Record<string, string>,
  fields: readonly string[],
  digits: string,
): boolean {
  return fields.some((field) => cnpjDigits(row[field]) === digits);
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
  const fundosByCnpj = (
    await scanZipCsvForNeedles(zip, "registro_fundo.csv", needles, Math.max(limit, CATALOG_CLASS_CAP))
  ).filter((row) => fieldCnpjEquals(row, ["CNPJ_Fundo"], digits));
  const classesByCnpj = (
    await scanZipCsvForNeedles(zip, "registro_classe.csv", needles, CATALOG_CLASS_CAP)
  ).filter((row) => fieldCnpjEquals(row, ["CNPJ_Classe"], digits));
  const keepIds = new Set(fundosByCnpj.map((row) => row.ID_Registro_Fundo ?? ""));
  for (const row of classesByCnpj) {
    keepIds.add(row.ID_Registro_Fundo ?? "");
  }
  const fundos =
    fundosByCnpj.length > 0
      ? fundosByCnpj
      : await scanZipCsv(zip, "registro_fundo.csv", (row) => keepIds.has(row.ID_Registro_Fundo ?? ""), limit);
  const classes = await scanZipCsv(
    zip,
    "registro_classe.csv",
    (row) => keepIds.has(row.ID_Registro_Fundo ?? ""),
    CATALOG_CLASS_CAP,
  );
  const classIds = new Set(classes.map((row) => row.ID_Registro_Classe ?? ""));
  const subclasses = await scanZipCsv(
    zip,
    "registro_subclasse.csv",
    (row) => classIds.has(row.ID_Registro_Classe ?? ""),
    CATALOG_CLASS_CAP,
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
  const fundos = await scanZipCsv(
    zip,
    "registro_fundo.csv",
    (row) => (row.Denominacao_Social ?? "").toLowerCase().includes(needle),
    limit,
  );
  if (fundos.length === 0) {
    return [];
  }
  const fundoIds = new Set(fundos.map((row) => row.ID_Registro_Fundo ?? ""));
  const classes = await scanZipCsv(
    zip,
    "registro_classe.csv",
    (row) => fundoIds.has(row.ID_Registro_Fundo ?? ""),
    CATALOG_CLASS_CAP,
  );
  const classIds = new Set(classes.map((row) => row.ID_Registro_Classe ?? ""));
  const subclasses = await scanZipCsv(
    zip,
    "registro_subclasse.csv",
    (row) => classIds.has(row.ID_Registro_Classe ?? ""),
    CATALOG_CLASS_CAP,
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

function formatYm(year: number, month: number): string {
  return `${year}${String(month).padStart(2, "0")}`;
}

function addMonths(year: number, month: number, delta: number): { year: number; month: number } {
  const absolute = year * 12 + (month - 1) + delta;
  return { year: Math.floor(absolute / 12), month: (absolute % 12) + 1 };
}

function lookbackMonths(
  endYear: number,
  endMonth: number,
  count: number,
): { year: number; month: number }[] {
  const out: { year: number; month: number }[] = [];
  for (let i = count - 1; i >= 0; i -= 1) {
    out.push(addMonths(endYear, endMonth, -i));
  }
  return out;
}

export function listCvmZipMonths(html: string, prefix: string): string[] {
  const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`${escaped}(\\d{6})\\.zip`, "gi");
  const months = new Set<string>();
  for (const match of html.matchAll(re)) {
    months.add(match[1]!);
  }
  return [...months].sort();
}

async function listPublishedMonths(url: string, prefix: string): Promise<string[]> {
  const html = new TextDecoder("utf-8").decode(
    await getBytes(url, { maxBytes: CVM_LISTING_MAX_BYTES, timeoutMs: 15_000 }),
  );
  return listCvmZipMonths(html, prefix);
}

async function resolveYearMonth(
  args: { year?: number; month?: number },
  listingUrl: string,
  prefix: string,
): Promise<{ year: number; month: number } | { error: string }> {
  const hasYear = args.year !== undefined;
  const hasMonth = args.month !== undefined;
  if (hasYear !== hasMonth) {
    return { error: "pass both `year` and `month`, or omit both for the latest published file" };
  }
  if (hasYear && hasMonth) {
    if (args.year! < 2018 || args.month! < 1 || args.month! > 12) {
      return { error: "year must be >= 2018 and month 1-12" };
    }
    return { year: args.year!, month: args.month! };
  }
  const published = await listPublishedMonths(listingUrl, prefix);
  const latest = published.at(-1);
  if (!latest) {
    return { error: `no published files at ${listingUrl}` };
  }
  return { year: Number(latest.slice(0, 4)), month: Number(latest.slice(4, 6)) };
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

function cdaBlockLabel(filename: string): string {
  const base = filename.split("/").pop() ?? filename;
  const upper = base.toUpperCase();
  const parts = base.replace(/\.csv$/i, "").split("_");
  if (parts.length >= 4 && parts[2] === "BLC") {
    return `BLC_${parts[3]}`;
  }
  if (upper.includes("CONFID")) {
    return base.toLowerCase().includes("fie") ? "FIE_CONFID" : "CONFID";
  }
  if (base.toLowerCase().startsWith("cda_fie")) {
    return "FIE";
  }
  if (upper.includes("_PL_")) {
    return "PL";
  }
  return "OTHER";
}

function mapHolding(row: Record<string, string>, bloco: string) {
  return {
    cnpj: row.CNPJ_FUNDO_CLASSE || row.CNPJ_FUNDO || "",
    nome_fundo: row.DENOM_SOCIAL || row.DENOM_CLASSE || "",
    dt_referencia: row.DT_COMPTC ?? "",
    bloco,
    tipo_aplicacao: row.TP_APLIC || null,
    tipo_ativo: row.TP_ATIVO || null,
    emissor: row.EMISSOR_LIGADO || row.EMISSOR || null,
    cnpj_emissor: row.CNPJ_EMISSOR || row.CPF_CNPJ_EMISSOR || null,
    tipo_negociacao: row.TP_NEGOC || null,
    quantidade_final: optFloat(row.QT_POS_FINAL),
    valor_mercado: optFloat(row.VL_MERC_POS_FINAL || row.VL_MERCADO || row.VL_MERC_POSICAO),
    descricao: row.DS_ATIVO || row.CD_ATIVO || null,
  };
}

function parseBlocks(raw: string | undefined): Set<string> | null {
  if (!raw?.trim()) {
    return null;
  }
  return new Set(
    raw
      .split(",")
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean),
  );
}

async function dailySeries(
  digits: string,
  year: number,
  month: number,
  limit: number,
): Promise<ReturnType<typeof mapDaily>[]> {
  const ym = formatYm(year, month);
  const zip = await fetchCvmZip(DAILY_URL.replace("{ym}", ym));
  const csvName = `inf_diario_fi_${ym}.csv`;
  const rows = (
    await scanZipCsvForNeedles(zip, csvName, cnpjNeedles(digits), Math.min(limit, DAILY_SCAN_CAP))
  ).filter((row) => fieldCnpjEquals(row, ["CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"], digits));
  return rows.map(mapDaily);
}

async function holdingsFromZip(
  zip: Uint8Array,
  digits: string,
  blocks: Set<string> | null,
  limit: number,
) {
  const needles = cnpjNeedles(digits);
  const holdings: ReturnType<typeof mapHolding>[] = [];
  for (const name of listZipEntryNames(zip)) {
    if (!name.toLowerCase().endsWith(".csv")) {
      continue;
    }
    const bloco = cdaBlockLabel(name);
    if (blocks && !blocks.has(bloco)) {
      continue;
    }
    const rows = (
      await scanZipCsvForNeedles(zip, name, needles, Math.min(limit - holdings.length, HOLDINGS_SCAN_CAP))
    ).filter((row) => fieldCnpjEquals(row, ["CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"], digits));
    for (const row of rows) {
      holdings.push(mapHolding(row, bloco));
      if (holdings.length >= limit) {
        return holdings;
      }
    }
  }
  return holdings;
}

export async function cvmFund(args: {
  dataset?: CvmDataset;
  cnpj?: string;
  q?: string;
  year?: number;
  month?: number;
  months?: number;
  product?: CvmPeriodProduct;
  blocks?: string;
  limit?: number;
}) {
  const dataset = args.dataset ?? "catalog";
  const limit = Math.min(
    args.limit ?? (dataset === "holdings" ? 2000 : dataset === "daily" ? 500 : 20),
    dataset === "daily" || dataset === "holdings" ? 2000 : 100,
  );

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

  if (dataset === "periods") {
    const product = args.product ?? "CDA";
    const listingUrl = product === "CDA" ? CDA_LISTING_URL : DAILY_LISTING_URL;
    const prefix = product === "CDA" ? "cda_fi_" : "inf_diario_fi_";
    const periods = await listPublishedMonths(listingUrl, prefix);
    return jsonResult({
      source: product === "CDA" ? "cvm_cda" : "cvm_inf_diario",
      product,
      latest: periods.at(-1) ?? null,
      periods,
    });
  }

  const digits = cnpjDigits(args.cnpj);
  if (digits.length < 8) {
    return errorResult(`dataset=${dataset} requires \`cnpj\``);
  }

  if (dataset === "holdings") {
    const resolved = await resolveYearMonth(args, CDA_LISTING_URL, "cda_fi_");
    if ("error" in resolved) {
      return errorResult(resolved.error);
    }
    const ym = formatYm(resolved.year, resolved.month);
    const zip = await fetchCvmZip(CDA_URL.replace("{ym}", ym));
    const holdings = await holdingsFromZip(zip, digits, parseBlocks(args.blocks), limit);
    return jsonResult({
      source: "cvm_cda",
      year: resolved.year,
      month: resolved.month,
      cnpj: digits,
      truncated: holdings.length >= limit,
      note: "CDA is a delayed monthly feed. CONFID rows are confidential (sigilo), not a complete open book.",
      holdings,
    });
  }

  const months = Math.min(Math.max(args.months ?? 1, 1), DAILY_MONTHS_MAX);
  const resolved = await resolveYearMonth(args, DAILY_LISTING_URL, "inf_diario_fi_");
  if ("error" in resolved) {
    return errorResult(resolved.error);
  }
  const window = lookbackMonths(resolved.year, resolved.month, months);
  const series: ReturnType<typeof mapDaily>[] = [];
  const missing: string[] = [];
  let remaining = limit;
  for (const stamp of window) {
    const ym = formatYm(stamp.year, stamp.month);
    try {
      const chunk = await dailySeries(digits, stamp.year, stamp.month, remaining);
      series.push(...chunk);
      remaining = Math.max(limit - series.length, 0);
      if (remaining === 0) {
        break;
      }
    } catch (error) {
      if (error instanceof UpstreamError && error.status === 404) {
        missing.push(ym);
        continue;
      }
      throw error;
    }
  }
  return jsonResult({
    source: "cvm_inf_diario",
    year: resolved.year,
    month: resolved.month,
    months,
    from: formatYm(window[0]!.year, window[0]!.month),
    to: formatYm(resolved.year, resolved.month),
    cnpj: digits,
    missing,
    series,
  });
}
