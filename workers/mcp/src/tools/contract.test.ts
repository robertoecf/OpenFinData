import assert from "node:assert/strict";
import { test } from "node:test";
import { buildUrl, parseJsonBody } from "../lib/http.ts";
import { brtNow, emptyDayReason } from "../lib/ptaxDay.ts";
import { envelopeBody, filterEntes, fold } from "./tesouro.ts";

// 2026-10-15 is a Thursday; 2026-10-10 is a Saturday.
const THU_11H_BRT = Date.parse("2026-10-15T14:00:00Z"); // 11h BRT
const THU_14H_BRT = Date.parse("2026-10-15T17:30:00Z"); // 14h30 BRT

test("brtNow shifts UTC by a fixed -3 offset", () => {
  assert.deepEqual(brtNow(THU_11H_BRT), { date: "2026-10-15", hour: 11 });
  // 01h UTC is still the previous day in BRT
  assert.deepEqual(brtNow(Date.parse("2026-10-16T01:00:00Z")), {
    date: "2026-10-15",
    hour: 22,
  });
});

test("emptyDayReason separates the four reasons a PTAX day can be empty", () => {
  assert.equal(emptyDayReason("2026-10-10", THU_11H_BRT).reason, "non_business_day");
  assert.equal(emptyDayReason("2027-01-01", THU_11H_BRT).reason, "future_date");
  // same day, before the ~13h BRT publication
  assert.equal(emptyDayReason("2026-10-15", THU_11H_BRT).reason, "not_published_yet");
  // same day, after publication: a holiday is the remaining explanation
  assert.equal(emptyDayReason("2026-10-15", THU_14H_BRT).reason, "no_quote_for_date");
  // a past business day never reports "not published yet"
  assert.equal(emptyDayReason("2026-10-14", THU_11H_BRT).reason, "no_quote_for_date");
});

test("emptyDayReason always carries a human-readable note", () => {
  for (const day of ["2026-10-10", "2027-01-01", "2026-10-15", "2026-10-14"]) {
    const { note } = emptyDayReason(day, THU_11H_BRT);
    assert.ok(note.includes(day), `note should name the date: ${note}`);
  }
});

test("fold makes matching case and accent insensitive", () => {
  assert.equal(fold("Várzea Grande"), "varzea grande");
  assert.equal(fold("SÃO PAULO"), "sao paulo");
  assert.equal(fold(null), "");
  assert.equal(fold(undefined), "");
});

const ROWS: Record<string, unknown>[] = [
  { cod_ibge: 3550308, uf: "SP", instituicao: "São Paulo", esfera: "M", populacao: 11451245 },
  { cod_ibge: 3509502, uf: "SP", instituicao: "Campinas", esfera: "M", populacao: 1139047 },
  { cod_ibge: 5108402, uf: "MT", instituicao: "Várzea Grande", esfera: "M", populacao: 318922 },
  { cod_ibge: 35, uf: "SP", ente: "Estado de São Paulo", esfera: "E", populacao: 44420459 },
];

test("filterEntes narrows by uf, esfera and accent-insensitive name", () => {
  assert.equal(filterEntes(ROWS, {}).length, 4);
  assert.equal(filterEntes(ROWS, { uf: "SP" }).length, 3);
  assert.equal(filterEntes(ROWS, { uf: "sp" }).length, 3, "uf match ignores case");
  assert.equal(filterEntes(ROWS, { esfera: "E" }).length, 1);

  const varzea = filterEntes(ROWS, { q: "varzea grande" });
  assert.equal(varzea.length, 1);
  assert.equal(varzea[0].cod_ibge, 5108402);

  assert.equal(filterEntes(ROWS, { uf: "SP", esfera: "M" }).length, 2, "filters compose");
});

test("filterEntes falls back to `ente` when `instituicao` is absent", () => {
  const estado = filterEntes(ROWS, { esfera: "E" });
  assert.equal(estado[0].instituicao, "Estado de São Paulo");
});

test("filterEntes keeps populacao null rather than dropping the row", () => {
  const out = filterEntes([{ cod_ibge: 1, uf: "AC", instituicao: "X", esfera: "M" }], {});
  assert.equal(out.length, 1);
  assert.equal(out[0].populacao, null);
});

test("envelopeBody reports truncation so an agent knows it did not see everything", () => {
  const many = Array.from({ length: 250 }, (_, i) => i);
  const cut = envelopeBody("entes", many, 100, "narrow it");
  assert.equal(cut.total_matched, 250);
  assert.equal(cut.returned, 100);
  assert.equal(cut.limit, 100);
  assert.equal(cut.truncated, true);
  assert.equal(cut.hint, "narrow it");
  assert.equal((cut.entes as number[]).length, 100);
});

test("envelopeBody omits the hint when nothing was cut", () => {
  const whole = envelopeBody("rows", [1, 2, 3], 100, "narrow it");
  assert.equal(whole.total_matched, 3);
  assert.equal(whole.returned, 3);
  assert.equal(whole.truncated, false);
  assert.ok(!("hint" in whole), "no hint when the caller saw everything");
});

test("envelopeBody keys the payload under the caller's name", () => {
  assert.ok("entes" in envelopeBody("entes", [], 10, "h"));
  assert.ok("rows" in envelopeBody("rows", [], 10, "h"));
});

test("buildUrl encodes spaces as %20, not + (Olinda OData rejects +)", () => {
  const url = buildUrl("https://example.com/odata/Foo", {
    $top: 20,
    $orderby: "Data desc",
    $filter: "Indicador eq 'IPCA'",
  });
  assert.ok(!url.search.includes("+"), `found + in ${url.search}`);
  assert.ok(url.search.includes("%24orderby=Data%20desc"));
  assert.ok(url.search.includes("Indicador%20eq%20%27IPCA%27"));
});

test("buildUrl keeps a literal + in a value escaped as %2B", () => {
  assert.equal(buildUrl("https://example.com/x", { q: "a+b" }).search, "?q=a%2Bb");
});

test("buildUrl skips undefined and empty values", () => {
  const url = buildUrl("https://example.com/x", { a: "1", b: undefined, c: "" });
  assert.equal(url.search, "?a=1");
});

test("parseJsonBody names the real condition when upstream returns HTML", () => {
  assert.throws(
    () => parseJsonBody('<?xml version="1.0"?><html><title>Requisicao invalida!</title>', "https://x/y"),
    /non-JSON body for https:\/\/x\/y/,
  );
});

test("parseJsonBody passes valid JSON through", () => {
  assert.deepEqual(parseJsonBody('{"a":1}', "https://x/y"), { a: 1 });
});

test("envelopeBody refuses to certify completeness the page cap cannot know", () => {
  const body = envelopeBody("rows", [1, 2, 3], 10, "narrow it", false);
  assert.equal(body.returned, 3);
  assert.equal(body.upstream_complete, false);
  assert.equal(body.truncated, true, "an unexhausted upstream must not look complete");
  assert.match(String(body.hint), /page cap/);
});

test("envelopeBody reports complete when it was cut only to limit", () => {
  const body = envelopeBody("rows", [1, 2, 3], 2, "narrow it", true);
  assert.equal(body.truncated, true);
  assert.equal(body.upstream_complete, true);
  assert.equal(body.hint, "narrow it");
});

test("envelopeBody leaves no hint when nothing was hidden", () => {
  const body = envelopeBody("rows", [1, 2], 10, "narrow it", true);
  assert.equal(body.truncated, false);
  assert.equal(body.upstream_complete, true);
  assert.ok(!("hint" in body));
});

test("the pre-13h PTAX note suggests rather than asserts a cause", () => {
  const { reason, note } = emptyDayReason("2026-10-15", THU_11H_BRT);
  assert.equal(reason, "not_published_yet");
  assert.match(note, /may not be out yet/);
  assert.match(note, /holiday/);
});
