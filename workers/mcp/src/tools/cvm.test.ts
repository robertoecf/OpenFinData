import assert from "node:assert/strict";
import { deflateRawSync } from "node:zlib";
import { afterEach, test } from "node:test";
import { cvmFund, listCvmZipMonths, relatedQuoteCnpjs } from "./cvm.ts";
import { listZipEntryNames, scanZipCsvForNeedles, zipFile } from "../lib/zipCsv.ts";

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

function mockRoutes(routes: Array<{ match: string; body: Uint8Array | string; status?: number }>) {
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    const route = routes
      .filter((item) => url.includes(item.match))
      .sort((a, b) => b.match.length - a.match.length)[0];
    if (!route) {
      return new Response("missing", { status: 404 });
    }
    return new Response(route.body, { status: route.status ?? 200 });
  }) as typeof fetch;
}

function mockZip(urlContains: string, zip: Uint8Array) {
  mockRoutes([{ match: urlContains, body: zip }]);
}

const CDA_HTML =
  '<a href="cda_fi_202606.zip">cda_fi_202606.zip</a><a href="cda_fi_202607.zip">cda_fi_202607.zip</a>';
const INF_HTML =
  '<a href="inf_diario_fi_202607.zip">inf_diario_fi_202607.zip</a><a href="inf_diario_fi_202608.zip">inf_diario_fi_202608.zip</a>';

const CDA_BLC1 =
  "CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;TP_ATIVO;EMISSOR;QT_POS_FINAL;VL_MERC_POS_FINAL;DS_ATIVO\n" +
  "38.729.027/0001-92;AMW PREV;2026-07-31;Titulos Publicos;LFT;TESOURO;10;1000;LFT 2027\n" +
  "21.494.444/0001-09;OUTRO;2026-07-31;Titulos Publicos;LFT;TESOURO;1;10;LFT 2027\n";
const CDA_BLC2 =
  "CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;TP_ATIVO;EMISSOR;QT_POS_FINAL;VL_MERC_POS_FINAL;DS_ATIVO\n" +
  "38.729.027/0001-92;AMW PREV;2026-07-31;Cotas de Fundos;Cota;OUTRO FUNDO;5;500;Fundo X\n";
const CDA_CONFID =
  "CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC\n" +
  "38.729.027/0001-92;AMW PREV;2026-07-31;Sigilo\n";

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

test("scanZipCsvForNeedles streams deflated CSV without requiring zipFile", async () => {
  const zip = deflateZip({ "registro_fundo.csv": FUNDO_CSV });
  const rows = await scanZipCsvForNeedles(zip, "registro_fundo.csv", ["38729027000192"], 5);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.CNPJ_Fundo, "38729027000192");
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

test("cvm_fund catalog ignores administrator CNPJ in the same row", async () => {
  mockZip(
    "registro_fundo_classe.zip",
    storeZip({
      "registro_fundo.csv": FUNDO_CSV,
      "registro_classe.csv": CLASSE_CSV,
      "registro_subclasse.csv": SUB_CSV,
    }),
  );
  const result = await cvmFund({ dataset: "catalog", cnpj: "59.281.253/0001-23" });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as unknown[];
  assert.equal(body.length, 0);
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

test("listCvmZipMonths reads only matching monthly zips", () => {
  const months = listCvmZipMonths(
    `${CDA_HTML}<a href="cda_fie_202607.zip">skip</a><a href="readme.txt">no</a>`,
    "cda_fi_",
  );
  assert.deepEqual(months, ["202606", "202607"]);
});

test("listZipEntryNames walks every local header", () => {
  const zip = storeZip({ "a.csv": "x\n", "b.csv": "y\n" });
  assert.deepEqual(listZipEntryNames(zip), ["a.csv", "b.csv"]);
});

test("cvm_fund periods lists CDA stamps and latest", async () => {
  mockRoutes([{ match: "/CDA/DADOS/", body: CDA_HTML }]);
  const result = await cvmFund({ dataset: "periods" });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as { latest: string; periods: string[] };
  assert.equal(body.latest, "202607");
  assert.deepEqual(body.periods, ["202606", "202607"]);
});

test("cvm_fund holdings requires cnpj", async () => {
  const result = await cvmFund({ dataset: "holdings", year: 2026, month: 7 });
  assert.equal(result.isError, true);
});

test("cvm_fund holdings scans every CDA block for one CNPJ", async () => {
  mockRoutes([
    {
      match: "cda_fi_202607.zip",
      body: storeZip({
        "cda_fi_BLC_1_202607.csv": CDA_BLC1,
        "cda_fi_BLC_2_202607.csv": CDA_BLC2,
        "cda_fi_CONFID_202607.csv": CDA_CONFID,
      }),
    },
  ]);
  const result = await cvmFund({
    dataset: "holdings",
    cnpj: "38729027000192",
    year: 2026,
    month: 7,
  });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as {
    holdings: Array<{ bloco: string; valor_mercado: number | null }>;
  };
  assert.equal(body.holdings.length, 3);
  assert.deepEqual(
    body.holdings.map((row) => row.bloco),
    ["BLC_1", "BLC_2", "CONFID"],
  );
  assert.equal(body.holdings[0]?.valor_mercado, 1000);
});

test("cvm_fund holdings omits year/month and uses the latest CDA stamp", async () => {
  mockRoutes([
    { match: "/CDA/DADOS/", body: CDA_HTML },
    {
      match: "cda_fi_202607.zip",
      body: storeZip({ "cda_fi_BLC_1_202607.csv": CDA_BLC1 }),
    },
  ]);
  const result = await cvmFund({ dataset: "holdings", cnpj: "38.729.027/0001-92" });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as { year: number; month: number; holdings: unknown[] };
  assert.equal(body.year, 2026);
  assert.equal(body.month, 7);
  assert.equal(body.holdings.length, 1);
});

test("cvm_fund holdings honors a block whitelist", async () => {
  mockRoutes([
    {
      match: "cda_fi_202607.zip",
      body: storeZip({
        "cda_fi_BLC_1_202607.csv": CDA_BLC1,
        "cda_fi_BLC_2_202607.csv": CDA_BLC2,
      }),
    },
  ]);
  const result = await cvmFund({
    dataset: "holdings",
    cnpj: "38729027000192",
    year: 2026,
    month: 7,
    blocks: "BLC_2",
  });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as { holdings: Array<{ bloco: string }> };
  assert.equal(body.holdings.length, 1);
  assert.equal(body.holdings[0]?.bloco, "BLC_2");
});

test("cvm_fund daily months=2 concatenates two INF_DIARIO months", async () => {
  const july =
    "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n" +
    "CLASSES - FIF;38.729.027/0001-92;;2026-07-31;1;2.90;100;0;0;1\n";
  mockRoutes([
    { match: "inf_diario_fi_202607.zip", body: storeZip({ "inf_diario_fi_202607.csv": july }) },
    { match: "inf_diario_fi_202608.zip", body: storeZip({ "inf_diario_fi_202608.csv": DAILY_CSV }) },
  ]);
  const result = await cvmFund({
    dataset: "daily",
    cnpj: "38729027000192",
    year: 2026,
    month: 8,
    months: 2,
  });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as {
    from: string;
    to: string;
    series: Array<{ dt_comptc: string; vl_quota: number }>;
  };
  assert.equal(body.from, "202607");
  assert.equal(body.to, "202608");
  assert.equal(body.series.length, 2);
  assert.equal(body.series[0]?.vl_quota, 2.9);
  assert.equal(body.series[1]?.vl_quota, 2.94);
});

test("cvm_fund catalog matches a class-only name", async () => {
  const classeOnly =
    CLASSE_CSV +
    "66089;99999;21494444000109;1;2024-12-02;2015-02-04;2024-12-02;Classes de Cotas de Fundos FIF;" +
    "SERIE SENIOR UNICA XYZ;Em Funcionamento Normal;2024-12-02;Renda Fixa;DI;N;Previdência RF;;;N;N;Aberto;N;Público;1;2026-08-26;1;AUD;2;CUST;3;CTRL\n";
  mockZip(
    "registro_fundo_classe.zip",
    storeZip({
      "registro_fundo.csv": FUNDO_CSV,
      "registro_classe.csv": classeOnly,
      "registro_subclasse.csv": SUB_CSV,
    }),
  );
  const result = await cvmFund({ dataset: "catalog", q: "serie senior unica xyz" });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as Array<{ cnpj: string }>;
  assert.equal(body.length, 1);
  assert.equal(body[0]?.cnpj, "38729027000192");
});

test("relatedQuoteCnpjs stitches only a single-class sibling CNPJ", () => {
  const single = relatedQuoteCnpjs(
    [
      {
        cnpj: "11111111000191",
        nome: "FUNDO",
        classes: [
          {
            cnpj_classe: "22222222000191",
            nome: "CLASSE",
            tipo_classe: "FIF",
            classificacao: "Multimercado",
            classe_anbima: "Livre",
            subclasses: [],
          },
        ],
      },
    ],
    "22222222000191",
  );
  assert.deepEqual(single, ["22222222000191", "11111111000191"]);
  const multi = relatedQuoteCnpjs(
    [
      {
        cnpj: "11111111000191",
        nome: "FUNDO",
        classes: [
          {
            cnpj_classe: "22222222000191",
            nome: "A",
            tipo_classe: "FIF",
            classificacao: "RF",
            classe_anbima: "",
            subclasses: [],
          },
          {
            cnpj_classe: "33333333000191",
            nome: "B",
            tipo_classe: "FIF",
            classificacao: "RF",
            classe_anbima: "",
            subclasses: [],
          },
        ],
      },
    ],
    "22222222000191",
  );
  assert.deepEqual(multi, ["22222222000191"]);
});

test("cvm_fund daily start/end stitches 555 fund CNPJ onto a single class", async () => {
  const fundo =
    "ID_Registro_Fundo;CNPJ_Fundo;Codigo_CVM;Denominacao_Social;Situacao;Data_Adaptacao_RCVM175\n" +
    "1;11111111000191;1;FUNDO LEGADO;Em Funcionamento Normal;2024-09-01\n";
  const classe =
    "ID_Registro_Fundo;ID_Registro_Classe;CNPJ_Classe;Codigo_CVM;Denominacao_Social;Situacao;Classificacao;Classificacao_Anbima;Tipo_Classe;Forma_Condominio\n" +
    "1;10;22222222000191;2;CLASSE CONTINUACAO;Em Funcionamento Normal;Multimercado;Livre;FIF;Aberto\n";
  const oldDaily =
    "TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n" +
    "FI;11.111.111/0001-91;2024-08-30;1;1.10;100;0;0;1\n";
  const newDaily =
    "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n" +
    "CLASSES - FIF;22.222.222/0001-91;;2024-09-02;1;1.20;110;0;0;1\n";
  mockRoutes([
    {
      match: "registro_fundo_classe.zip",
      body: storeZip({
        "registro_fundo.csv": fundo,
        "registro_classe.csv": classe,
        "registro_subclasse.csv": SUB_CSV,
      }),
    },
    { match: "inf_diario_fi_202408.zip", body: storeZip({ "inf_diario_fi_202408.csv": oldDaily }) },
    { match: "inf_diario_fi_202409.zip", body: storeZip({ "inf_diario_fi_202409.csv": newDaily }) },
  ]);
  const result = await cvmFund({
    dataset: "daily",
    cnpj: "22222222000191",
    start: "2024-08-01",
    end: "2024-09-30",
  });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as {
    from: string;
    to: string;
    needles: string[];
    served: Array<{ nicename: string; points: number }>;
    series: Array<{ vl_quota: number }>;
  };
  assert.equal(body.from, "202408");
  assert.equal(body.to, "202409");
  assert.deepEqual(body.needles, ["22222222000191", "11111111000191"]);
  assert.equal(body.series.length, 2);
  assert.equal(body.served.length, 1);
  assert.equal(body.served[0]?.nicename, "CLASSE CONTINUACAO");
  assert.equal(body.served[0]?.points, 2);
});

test("cvm_fund daily does not collapse two subclasses", async () => {
  const daily =
    "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n" +
    "CLASSES - FIF;38.729.027/0001-92;S1;2026-08-03;1;1.00;100;0;0;1\n" +
    "CLASSES - FIF;38.729.027/0001-92;S2;2026-08-03;1;2.00;200;0;0;10\n";
  mockRoutes([
    {
      match: "registro_fundo_classe.zip",
      body: storeZip({
        "registro_fundo.csv": FUNDO_CSV,
        "registro_classe.csv": CLASSE_CSV,
        "registro_subclasse.csv":
          SUB_CSV +
          "12189;S1;1;2024-09-27;2024-09-27;SENIOR;Em Funcionamento Normal;2024-09-27;Aberto;N;Público;N;N;N\n" +
          "12189;S2;2;2024-09-27;2024-09-27;SUBORDINADA;Em Funcionamento Normal;2024-09-27;Aberto;N;Público;N;N;N\n",
      }),
    },
    { match: "inf_diario_fi_202608.zip", body: storeZip({ "inf_diario_fi_202608.csv": daily }) },
  ]);
  const result = await cvmFund({ dataset: "daily", cnpj: "38729027000192", year: 2026, month: 8 });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as {
    pick_required: boolean;
    served: Array<{ id_subclasse: string; nicename: string }>;
  };
  assert.equal(body.pick_required, true);
  assert.deepEqual(
    body.served.map((row) => row.id_subclasse).sort(),
    ["S1", "S2"],
  );
  assert.equal(body.served.find((row) => row.id_subclasse === "S2")?.nicename, "SUBORDINADA");
});

test("cvm_fund daily without year/month uses the latest INF_DIARIO stamp", async () => {
  mockRoutes([
    { match: "/INF_DIARIO/DADOS/", body: INF_HTML },
    {
      match: "inf_diario_fi_202608.zip",
      body: storeZip({ "inf_diario_fi_202608.csv": DAILY_CSV }),
    },
  ]);
  const result = await cvmFund({ dataset: "daily", cnpj: "38729027000192" });
  assert.equal(result.isError, undefined);
  const body = JSON.parse(result.content[0].text) as { year: number; month: number; series: unknown[] };
  assert.equal(body.year, 2026);
  assert.equal(body.month, 8);
  assert.equal(body.series.length, 1);
});
