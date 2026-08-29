import assert from "node:assert/strict";
import { deflateRawSync } from "node:zlib";
import { afterEach, test } from "node:test";
import { cvmFund } from "./cvm.ts";
import { zipFile } from "../lib/zipCsv.ts";

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function u16(value: number): Uint8Array {
  return Uint8Array.of(value & 0xff, (value >> 8) & 0xff);
}

function u32(value: number): Uint8Array {
  return Uint8Array.of(
    value & 0xff,
    (value >> 8) & 0xff,
    (value >> 16) & 0xff,
    (value >> 24) & 0xff,
  );
}

function zipEntries(files: Record<string, string>, method: 0 | 8): Uint8Array {
  const chunks: Uint8Array[] = [];
  for (const [name, text] of Object.entries(files)) {
    const payload = new TextEncoder().encode(text);
    const stored = method === 8 ? new Uint8Array(deflateRawSync(payload)) : payload;
    const filename = new TextEncoder().encode(name);
    const crc = crc32(payload);
    chunks.push(
      Uint8Array.of(0x50, 0x4b, 0x03, 0x04),
      u16(20),
      u16(0),
      u16(method),
      u16(0),
      u16(0),
      u32(crc),
      u32(stored.length),
      u32(payload.length),
      u16(filename.length),
      u16(0),
      filename,
      stored,
    );
  }
  const total = chunks.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of chunks) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function storeZip(files: Record<string, string>): Uint8Array {
  return zipEntries(files, 0);
}

function deflateZip(files: Record<string, string>): Uint8Array {
  return zipEntries(files, 8);
}

const FUNDO_CSV =
  "ID_Registro_Fundo;CNPJ_Fundo;Codigo_CVM;Data_Registro;Data_Constituicao;Tipo_Fundo;Denominacao_Social;Data_Cancelamento;Situacao;Data_Inicio_Situacao;Data_Adaptacao_RCVM175;Data_Inicio_Exercicio_Social;Data_Fim_Exercicio_Social;Patrimonio_Liquido;Data_Patrimonio_Liquido;Diretor;CNPJ_Administrador;Administrador;Tipo_Pessoa_Gestor;CPF_CNPJ_Gestor;Gestor\n" +
  "66089;38729027000192;377910;2020-09-28;2020-09-17;FI;AMW PREVIDÊNCIA GESTÃO ATIVA FUNDO DE INVESTIMENTO FINANCEIRO MULTIMERCADO;;Em Funcionamento Normal;2021-02-01;2024-09-27;2026-01-01;2026-12-31;55454535.34;2024-09-27;GUSTAVO;59281253000123;BTG;PJ;26737584000176;AMW ASSET MANAGEMENT LTDA\n";

const CLASSE_CSV =
  "ID_Registro_Fundo;ID_Registro_Classe;CNPJ_Classe;Codigo_CVM;Data_Registro;Data_Constituicao;Data_Inicio;Tipo_Classe;Denominacao_Social;Situacao;Data_Inicio_Situacao;Classificacao;Indicador_Desempenho;Classe_Cotas;Classificacao_Anbima;Tributacao_Longo_Prazo;Entidade_Investimento;Permitido_Aplicacao_CemPorCento_Exterior;Classe_ESG;Forma_Condominio;Exclusivo;Publico_Alvo;Patrimonio_Liquido;Data_Patrimonio_Liquido;CNPJ_Auditor;Auditor;CNPJ_Custodiante;Custodiante;CNPJ_Controlador;Controlador\n" +
  "66089;12189;38729027000192;65510;2024-09-27;2020-09-17;2024-09-27;Classes de Cotas de Fundos FIF;AMW PREVIDÊNCIA GESTÃO ATIVA;Em Funcionamento Normal;2024-09-27;Multimercado;DI;N;Previdência Multimercado Livre;;;N;N;Aberto;S;Profissional;29428273.87;2026-08-26;1;AUD;2;CUST;3;CTRL\n";

const SUB_CSV =
  "ID_Registro_Classe;ID_Subclasse;Codigo_CVM;Data_Constituicao;Data_Inicio;Denominacao_Social;Situacao;Data_Inicio_Situacao;Forma_Condominio;Exclusivo;Publico_Alvo;Previdenciario;Exclusivo_INR;Exclusivo_Previdencia_Complementar\n";

const DAILY_CSV =
  "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n" +
  "CLASSES - FIF;38.729.027/0001-92;;2026-08-03;1;2.94;100;0;0;1\n" +
  "CLASSES - FIF;21.494.444/0001-09;;2026-08-03;1;2.95;200;0;0;1\n";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockZip(urlContains: string, zip: Uint8Array) {
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (!url.includes(urlContains)) {
      return new Response("missing", { status: 404 });
    }
    return new Response(zip, { status: 200 });
  }) as typeof fetch;
}

test("zipFile reads stored CSV", async () => {
  const zip = storeZip({ "registro_fundo.csv": FUNDO_CSV });
  const bytes = await zipFile(zip, "registro_fundo.csv");
  assert.match(new TextDecoder().decode(bytes), /38729027000192/);
});

test("zipFile inflates deflated CSV (CVM method 8)", async () => {
  const zip = deflateZip({ "registro_fundo.csv": FUNDO_CSV });
  const bytes = await zipFile(zip, "registro_fundo.csv");
  assert.match(new TextDecoder().decode(bytes), /38729027000192/);
});

test("cvm_fund catalog requires cnpj or q", async () => {
  const result = await cvmFund({ dataset: "catalog" });
  assert.equal(result.isError, true);
});

test("cvm_fund catalog resolves punctuated CNPJ", async () => {
  mockZip(
    "registro_fundo_classe.zip",
    storeZip({
      "registro_fundo.csv": FUNDO_CSV,
      "registro_classe.csv": CLASSE_CSV,
      "registro_subclasse.csv": SUB_CSV,
    }),
  );
  const result = await cvmFund({ dataset: "catalog", cnpj: "38.729.027/0001-92" });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as Array<{
    cnpj: string;
    classes: Array<{ forma_condominio: string; classificacao: string }>;
  }>;
  assert.equal(body.length, 1);
  assert.equal(body[0]?.cnpj, "38729027000192");
  assert.equal(body[0]?.classes[0]?.forma_condominio, "Aberto");
  assert.equal(body[0]?.classes[0]?.classificacao, "Multimercado");
});

test("cvm_fund daily matches digit CNPJ to punctuated INF_DIARIO", async () => {
  mockZip(
    "inf_diario_fi_202608.zip",
    storeZip({ "inf_diario_fi_202608.csv": DAILY_CSV }),
  );
  const result = await cvmFund({
    dataset: "daily",
    cnpj: "38729027000192",
    year: 2026,
    month: 8,
  });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as { series: Array<{ cnpj: string; vl_quota: number }> };
  assert.equal(body.series.length, 1);
  assert.equal(body.series[0]?.cnpj, "38.729.027/0001-92");
  assert.equal(body.series[0]?.vl_quota, 2.94);
});
