# Deploy privado: MCP Charlie (code mode)

MCP **privado** do Charlie (Wealthuman): FastAPI + gVisor +
`FINDATA_MCP_CODE_MODE=1`, publicado só via Cloudflare Tunnel + Access
(service token). Não é superfície pública.

| Superfície | Onde | Code mode |
|---|---|---|
| Público | Worker `workers/mcp` → `https://openfindata.com.br/mcp` | Não |
| Interno REST | gVisor Tailscale `100.90.45.18:8000` | Não |
| Charlie | `https://charlie-mcp.openfindata.com.br/mcp` | Sim |

## Arquitetura

```
Charlie (Wealthuman Worker / agent)
  → HTTPS charlie-mcp.openfindata.com.br
  → Cloudflare Access (service token headers)
  → Tunnel openfindata-charlie-mcp
  → origin checa X-Openfindata-Origin-Token
  → 127.0.0.1:8001
  → container openfindata-charlie-mcp (runsc, CODE_MODE=1)
```

O Worker público **não** alcança Tailscale e **não** deve proxyar este
host. Charlie chama o hostname Access-protegido com service token.

## Compose (VPS)

Arquivo: `deploy/docker-compose.charlie-mcp.yml`

- Porta: `127.0.0.1:8001:8000` (loopback only)
- Runtime: `runsc` (gVisor)
- Rede isolada: `openfindata_charlie_net`
- `FINDATA_MCP_CODE_MODE=1`
- `FINDATA_MCP_ORIGIN_TOKEN` obrigatório (compose e processo recusam subir sem ele)
- Healthcheck Docker desabilitado (mesmo motivo do stack gVisor público antigo)

```bash
cd /opt/openfindata-launch
# openssl rand -hex 32
export FINDATA_MCP_ORIGIN_TOKEN='...'   # persistir em deploy/.env (gitignored)
docker compose -f deploy/docker-compose.charlie-mcp.yml up -d --build
curl -sS http://127.0.0.1:8001/health
# /mcp no loopback sem X-Openfindata-Origin-Token deve ser 401
```

## Tunnel + Access

Já provisionado (conta Robertoecf / Access org Wealthuman):

| Recurso | Valor |
|---|---|
| Hostname | `charlie-mcp.openfindata.com.br` |
| Tunnel | `openfindata-charlie-mcp` |
| Ingress | `http://127.0.0.1:8001` |
| Access app | Charlie openfindata MCP |
| Service token name | `wealthuman-charlie-openfindata-mcp` |
| cloudflared unit | `cloudflared-charlie` |
| Token file | `/etc/cloudflared/openfindata-charlie.env` (root-only) |

Política Access: **somente** service token (sem e-mail / browser login).

O origin **não** confia só no Access. Com `CODE_MODE=1` o processo exige
`FINDATA_MCP_ORIGIN_TOKEN` no boot e o header `X-Openfindata-Origin-Token`
em todo path que não seja `/health`. O Charlie envia esse header junto
com o service token; Access não o stripa. Loopback sem o header → **401**.

### Headers obrigatórios

```http
CF-Access-Client-Id: <client_id>.access
CF-Access-Client-Secret: <client_secret>
X-Openfindata-Origin-Token: <origin token>
```

Guardar os três segredos no **Doppler Wealthuman** (nunca no git):

```text
OPENFINDATA_CHARLIE_MCP_URL=https://charlie-mcp.openfindata.com.br/mcp
OPENFINDATA_CHARLIE_CF_ACCESS_CLIENT_ID=...
OPENFINDATA_CHARLIE_CF_ACCESS_CLIENT_SECRET=...
OPENFINDATA_CHARLIE_ORIGIN_TOKEN=...
```

## Consumo MCP (Streamable HTTP)

fastapi-mcp é sessionful: use o `mcp-session-id` do `initialize` nas
chamadas seguintes.

```bash
# 1) initialize → gravar mcp-session-id do response header
# 2) notifications/initialized
# 3) tools/list ou tools/call com o mesmo session id
```

Tools esperadas: ~26, incluindo `findata_run_code`, registry, ANBIMA,
CVM/B3 paths (Python), além das séries públicas.

Smoke mínimo (substituir secrets do Doppler):

```bash
# Sem Access → 403
curl -sS -o /dev/null -w "%{http_code}\n" \
  https://charlie-mcp.openfindata.com.br/health

# Com Access → 200
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "CF-Access-Client-Id: $OPENFINDATA_CHARLIE_CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $OPENFINDATA_CHARLIE_CF_ACCESS_CLIENT_SECRET" \
  https://charlie-mcp.openfindata.com.br/health
```

`findata_run_code` com `print(1+1)` deve retornar `output: "2\n"`.

Preflight obrigatório (não basta `/health`):

```bash
# Loopback: MCP sem origin token
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H 'content-type: application/json' \
  -X POST http://127.0.0.1:8001/mcp \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"preflight","version":"0"}}}'
# 401

# Loopback: REST autenticado no origin
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "X-Openfindata-Origin-Token: $FINDATA_MCP_ORIGIN_TOKEN" \
  http://127.0.0.1:8001/stats
# 200

# Público: tools/list no Worker NÃO contém findata_run_code
```

## Operação

```bash
# Status
ssh monvanti-vps 'docker ps --filter name=openfindata-charlie; systemctl is-active cloudflared-charlie'

# Logs
ssh monvanti-vps 'docker logs --tail 100 openfindata-charlie-mcp'
ssh monvanti-vps 'journalctl -u cloudflared-charlie -n 50 --no-pager'

# Restart compose
ssh monvanti-vps 'cd /opt/openfindata-launch && docker compose -f deploy/docker-compose.charlie-mcp.yml up -d'
```

## Segurança

- Nunca publicar `8001` em `0.0.0.0` ou Traefik público.
- Nunca ligar `FINDATA_MCP_CODE_MODE=1` no Worker ou no compose gVisor
  Tailscale-only usado para REST interno.
- Sem `FINDATA_MCP_ORIGIN_TOKEN` o container Charlie **não sobe**.
- Rotacionar o service token **e** o origin token se vazou em chat/logs;
  atualizar Doppler (Access + `OPENFINDATA_CHARLIE_ORIGIN_TOKEN`) e o env do compose.
- Rate limit Charlie: `120/minute;5000/day` (compose).

## Wiring Wealthuman

No Charlie: MCP client Streamable HTTP apontando para
`OPENFINDATA_CHARLIE_MCP_URL` com Access **e** `X-Openfindata-Origin-Token`
em toda request (incluindo `initialize` e `tools/call`). Manter sessão
(`mcp-session-id`) por conversa/agent run.
