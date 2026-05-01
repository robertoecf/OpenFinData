# Deploy público do Dados Financeiros Abertos no seu PC (WSL + Cloudflare Tunnel)

> **Meta:** expor o **Dados Financeiros Abertos** como **servidor MCP público** — acessível via
> HTTPS, com TLS, rate limit, e _sem_ abrir porta no roteador nem pagar nada.
>
> **Stack:** Windows + WSL2 + Docker + Cloudflare Tunnel.
> **Custo:** R$ 0. **Tempo:** ~20 minutos do zero ao `https://findata.seudominio.com.br` público.

---

## Por que esse setup?

| Alternativa | Problema |
|---|---|
| Deixar porta 8000 aberta no roteador | NAT, IP dinâmico, sem TLS, alvo de bots |
| VPS (DigitalOcean, Hetzner) | R$ 40-100/mês fixo |
| ngrok free | URL muda a cada restart, limite de conexões |
| **Cloudflare Tunnel** | **Grátis, URL fixa, TLS automático, DDoS protegido, WAF incluído** |

O `cloudflared` faz um túnel _saindo_ do seu PC pra Cloudflare (outbound, nunca
inbound). Qualquer firewall/NAT funciona. A Cloudflare vira seu edge: termina
TLS, filtra bots, serve a URL `*.seudominio.com.br`.

---

## Pré-requisitos

- **Windows 10/11** com **WSL2** habilitado (`wsl --install`)
- **Ubuntu** (ou outra distro) dentro do WSL — `wsl --install -d Ubuntu`
- **Docker Desktop** com integração WSL ativa _(opcional — dá pra rodar sem Docker também)_
- Um **domínio registrado e apontando pra Cloudflare** (qualquer .com/.br funciona; a
  Cloudflare oferece conta grátis com DNS gerenciado)

---

## Caminho A — Docker Compose (recomendado)

### 1. Clone e build no WSL

```bash
# dentro do WSL
cd ~
git clone https://github.com/robertoecf/findata-br.git
cd findata-br
docker compose -f deploy/docker-compose.prod.yml build
```

### 2. Cadastre o Tunnel na Cloudflare

1. Entre em <https://one.dash.cloudflare.com> → **Networks** → **Tunnels** → **Create a tunnel**.
2. Escolha **Cloudflared**, dê um nome (ex.: `findata-br`).
3. Copie o **Tunnel Token** (string longa começando com `ey...`).
4. Na aba **Public Hostname** configure uma rota:
   - Subdomain: `findata`
   - Domain: `seudominio.com.br`
   - Service: `http://findata:8000`

### 3. Suba com o tunnel

```bash
# cria .env ao lado do compose
cat > deploy/.env <<EOF
CF_TUNNEL_TOKEN=ey...seu-token-aqui
EOF

docker compose -f deploy/docker-compose.prod.yml --profile tunnel \
  --env-file deploy/.env up -d
```

Pronto. Em ~30s:

```bash
curl https://findata.seudominio.com.br/health
# {"status":"ok","version":"0.1.0"}

curl https://findata.seudominio.com.br/stats
# { ... uptime, cache, rate limits ... }

curl https://findata.seudominio.com.br/bcb/series/name/selic?n=3
# dados reais vindo do BCB
```

---

## Caminho B — systemd + cloudflared nativo (sem Docker)

Use se quiser menos overhead ou se Docker Desktop te irrita.

### 1. Crie usuário e diretório

```bash
sudo useradd --system --create-home --home-dir /opt/findata-br findata
sudo mkdir -p /var/log/findata-br
sudo chown findata:findata /var/log/findata-br
```

### 2. Instale o Dados Financeiros Abertos

```bash
sudo -u findata bash <<'EOF'
cd /opt/findata-br
git clone https://github.com/robertoecf/findata-br.git .
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
EOF
```

### 3. Ative o serviço

```bash
sudo cp /opt/findata-br/deploy/findata-br.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now findata-br
sudo systemctl status findata-br
```

### 4. Instale o cloudflared

```bash
# Ubuntu/Debian
curl -L https://pkg.cloudflare.com/install.sh | sudo bash
sudo apt install cloudflared

# Autentica (abre browser no Windows)
cloudflared tunnel login

# Cria o tunnel e anota o UUID
cloudflared tunnel create findata-br

# Config em ~/.cloudflared/config.yml:
cat > ~/.cloudflared/config.yml <<EOF
tunnel: findata-br
credentials-file: /home/$USER/.cloudflared/<UUID>.json

ingress:
  - hostname: findata.seudominio.com.br
    service: http://localhost:8000
  - service: http_status:404
EOF

# DNS automático
cloudflared tunnel route dns findata-br findata.seudominio.com.br

# Instala como serviço systemd
sudo cloudflared service install
sudo systemctl start cloudflared
```

---

## Variáveis de ambiente importantes

| Variável | Default | O que faz |
|---|---|---|
| `FINDATA_RATE_LIMIT_ENABLED` | `true` | Liga/desliga o rate limiting |
| `FINDATA_RATE_LIMIT_DEFAULT` | `60/minute;1000/day` | Bucket por IP (`;`-separated) |

Formato dos buckets: `<N>/<period>` com `period` ∈ `{second, minute, hour, day}`.

Exemplos:
- Mais permissivo: `FINDATA_RATE_LIMIT_DEFAULT="120/minute;5000/day"`
- Mais restritivo: `FINDATA_RATE_LIMIT_DEFAULT="20/minute;500/day"`
- Sem limite (deploy interno): `FINDATA_RATE_LIMIT_ENABLED=false`

---

## Conectando o MCP no Claude Desktop / Cursor / Codex

Depois que a URL pública estiver respondendo, adicione em
`~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) ou o equivalente no seu cliente MCP:

```jsonc
{
  "mcpServers": {
    "findata-br": {
      "url": "https://findata.seudominio.com.br/mcp"
    }
  }
}
```

Reinicie o cliente. Ele vai enumerar todas as ~27 ferramentas
(`bcb_get_series_by_name`, `ipea_search`, `cvm_list_companies`, etc.) e
usá-las automaticamente quando você perguntar coisas como:

> _"Qual a Selic atual e como ela se compara com a expectativa do Focus pra 2027?"_

---

## Observabilidade

- `GET /health` — liveness probe (usar pra uptime monitors tipo BetterStack/UptimeRobot).
- `GET /stats` — snapshot (uptime, cache, versão, se rate-limit ativo).
- `GET /docs` — Swagger UI interativo pro endpoint público.
- Logs: `docker compose logs -f findata` ou `journalctl -u findata-br -f`.

### Uptime monitor grátis

1. <https://uptimerobot.com> → add monitor.
2. Type: HTTP(s).
3. URL: `https://findata.seudominio.com.br/health`.
4. Intervalo: 5 min.

---

## Hardening adicional (opcional)

### Cloudflare WAF rules

No painel da Cloudflare → **Security** → **WAF** → Custom Rules:

```
(http.request.uri.path matches "^/cvm/financials/") and (cf.threat_score gt 20)
→ Challenge
```

Bloqueia bots em endpoints pesados.

### Cache na edge

**Rules** → **Cache Rules**:

```
If hostname == "findata.seudominio.com.br" and URI path matches "^/(bcb|ibge)/"
→ Cache eligibility: Eligible for cache
→ Edge TTL: 10 minutes
```

Cacheia na borda. Sua casa recebe ~10% do tráfego mesmo com uso público.

---

## Compartilhando publicamente

Quando você estiver pronto pra divulgar:

1. **Tweet** com `https://findata.seudominio.com.br/docs` (Swagger é auto-demo).
2. **LinkedIn** BR dev/fintech: comunidade grande, ROI alto.
3. **Awesome lists** ([awesome-brazilian-opensource](https://github.com/pgugger/awesome-brazilian-opensource),
   [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)) — PR direto.
4. **Hacker News** Show HN.
5. **Discord**: [Claude Developers](https://discord.com/invite/anthropic), [Python Brasil](https://python.org.br/comunidade/).

O endpoint `/mcp` é plug-and-play no Claude Desktop — esse é seu melhor demo.

---

## Troubleshooting

**Tunnel não conecta:**
```bash
docker compose logs cloudflared
# ou
sudo journalctl -u cloudflared -f
```

**Dados Financeiros Abertos caiu silenciosamente:**
```bash
curl http://localhost:8000/health   # local
# se local OK mas público não, problema é no tunnel
```

**Rate limit mal calibrado:**
```bash
curl -I https://findata.seudominio.com.br/bcb/series
# Olhe os headers X-RateLimit-Limit / Remaining / Reset
```

**WSL parando de rodar quando fecho o terminal:**
Ative _WSL2 service mode_ no `wsl.conf`:
```ini
# /etc/wsl.conf dentro do WSL
[boot]
systemd=true
```
`wsl --shutdown` no Windows, reabre.

---

## Custo mensal realista

| Item | Custo |
|---|---|
| WSL + Ubuntu | R$ 0 |
| Docker Desktop (uso pessoal/open source) | R$ 0 |
| Cloudflare Tunnel + DNS + edge + WAF | R$ 0 |
| Domínio `.com.br` | ~R$ 40/ano |
| Energia elétrica do PC Gamer ligado 24/7 | ~R$ 30-60/mês |

Total: **~R$ 40/mês** no pior caso.

Mantendo o PC ligado só algumas horas por dia (com UptimeRobot só avisando):
**< R$ 10/mês**.
