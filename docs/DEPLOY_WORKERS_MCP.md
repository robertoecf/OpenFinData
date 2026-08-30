# Deploy público: MCP no Cloudflare Workers

A superfície **pública** do openfindata é um Worker (`workers/mcp`):
landing + MCP Streamable HTTP em `/mcp`.

O FastAPI Python **não** fica na internet. Ele roda na VPS (gVisor),
publicado só em loopback + IP Tailscale. REST/docs/CLI continuam aí.

## Por que não proxy para o FastAPI

O Worker **não alcança a Tailscale**. Encaminhar `/mcp` para a VPS
recolocaria o processo Python no caminho público (via token/túnel).
As tools deste Worker chamam fontes públicas oficiais: APIs JSON (BCB,
IBGE, IPEA, SICONFI, Open Finance Directory) e os ZIPs/CSV da CVM em
`dados.cvm.gov.br` para fundos abertos (`cvm_fund`).

Fora deste Worker (lâmina, perfil, B3 COTAHIST, ANBIMA XLS,
registry FTS5, code mode): `pip install openfindata` ou FastAPI interno.

`cvm_fund` no Worker:

- `dataset=catalog` + `cnpj` ou `q` — cadastro oficial RCVM 175
  (`registro_fundo_classe.zip`: fundo + classe + subclasse). `q` casa
  nome de fundo, classe e subclasse. `cad_fi.csv` não lista fundos já
  adaptados à Resolução 175.
- `dataset=daily` + `cnpj` — série de cotas INF_DIARIO. Sem `year`/`month`
  usa o mês mais recente; `months` (1–12) ou `start`/`end` (YYYY-MM-DD,
  no máximo 12 meses; janelas maiores pedem nova chamada). Classe única
  adaptada da 555 costura o CNPJ legado quando o arquivo CVM permite.
  `served[]` traz `nicename` / classe / subclasse efetivamente devolvidos;
  várias séries no mesmo CNPJ vêm agrupadas (`pick_required`) — não
  escolher FIDC sênior vs subordinada pelo usuário. ZIP anual HIST da CVM
  passa de 32 MB e não entra no isolate.
- `dataset=periods` — stamps YYYYMM publicados (`product=CDA` ou `INF_DIARIO`).
- `dataset=holdings` + `cnpj` — CDA (carteira). Sem `year`/`month` usa o
  CDA mais recente. Scan em stream por CNPJ; linhas `CONFID` são sigilo,
  não carteira aberta completa. Não usa Mais Retorno.

Mapeamento das tools de **dados** da Mais Retorno (cálculo/analytics fora):
`search_assets` / `get_asset_info` / `list_fund_structure` /
`get_fund_class_subclass` → `catalog`; `get_quotes` → `daily`;
`get_available_wallets` → `periods`; `get_wallet_detail` → `holdings`.

## Deploy

```bash
cd workers/mcp
npm install
npx wrangler deploy
```

Custom domain (depois do smoke em `*.workers.dev`):

```toml
# wrangler.toml
routes = [
  { pattern = "openfindata.com.br", custom_domain = true },
  { pattern = "www.openfindata.com.br", custom_domain = true },
]
```

O custom domain no Cloudflare precisa DNS proxied (laranja). O registro
A grey-cloud para o IP da VPS deve sair.

Smoke:

```bash
curl -sS https://openfindata.com.br/health
# POST JSON-RPC tools/list against /mcp with an MCP client
# tools/list NÃO deve incluir findata_run_code
```

Upstream calls no Worker têm timeout (15s) e teto de payload (2 MB;
8 MB no Directory Open Finance; 32 MB / 45s só em `cvm_fund`, porque
cadastro, INF_DIARIO e CDA vêm em ZIP). O Worker faz scan em stream do
CSV deflate (não materializa o CDA descompactado). Séries BCB sem
intervalo caem em `last_n≤200`. Rate limits de `/mcp` não mudam.

`/mcp` usa Workers Rate Limit bindings (não Cloudflare Queues): 60 req /
60s por IP e pico 20 / 10s. Overflow é síncrono: HTTP 429 + `Retry-After`
e corpo `{ "error": "rate_limited" }`. Landing `/` e `/health` ficam
fora do limite. Os contadores são por localização Cloudflare.

## FastAPI interno (Tailscale)

No compose gVisor: sem labels Traefik; portas `127.0.0.1:8000` e
`${TAILSCALE_IP}:8000`.

```bash
curl http://100.90.45.18:8000/health   # na Tailscale
curl http://127.0.0.1:8000/docs        # na própria VPS
```

Túnel Cloudflare (opcional, HTTPS interno): `cloudflared` → `127.0.0.1:8000`
com Access allowlist (e-mail / WARP). Isso **não** é o MCP público.

## Code mode

`findata_run_code` **não** entra no Worker público.

Para Charlie (Wealthuman): MCP privado com code mode via Tunnel + Access —
ver [DEPLOY_CHARLIE_MCP.md](./DEPLOY_CHARLIE_MCP.md).
