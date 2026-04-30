# Fontes com credenciais

> **Status atual: nenhuma fonte ativa exige credenciais.** O findata-br é
> 100% public-data — todas as 11 fontes públicas online (BCB, CVM, B3, IBGE,
> IPEA, Tesouro, ANBIMA, Receita Federal, ANEEL, SUSEP e Open Finance Brasil)
> funcionam apenas com `pip install findata-br`, sem env vars, sem cadastro,
> sem chave de API. O registro local também funciona offline. Este documento existe pra registrar o
> _framework_ que está pronto pra ser usado quando alguém da comunidade
> integrar uma fonte que de fato exija auth (SUSEP, BNDES, etc.).

## Princípios de design

1. **Zero credenciais embutidas.** O projeto nunca armazena, nunca
   compartilha, nunca embute API keys de ninguém.
2. **Cada operador traz as suas.** Quem quiser SUSEP/BNDES/etc abre
   conta com o provedor e passa as credenciais via env var.
3. **Fail-clean quando ausente.** Sem credenciais, as rotas devem
   retornar `503 Service Unavailable` com mensagem dizendo qual env
   var setar — nunca `401`, nunca crash.
4. **Tokens cacheados em processo.** OAuth2 client_credentials flow é
   feito uma vez; o token vive em memória até ~60s antes de expirar.
5. **Arquitetura genérica.** O módulo `findata.auth` serve qualquer
   fonte — basta uma subclasse de `OAuth2ClientCredentials` e um
   `load_<fonte>_credentials()` que lê env vars.

## Por que ANBIMA não está aqui

A versão 0.1 do findata-br tentou integrar ANBIMA via Sensedia API
(autenticada). O OAuth2 flow funciona, mas o programa de developers da
ANBIMA não é self-serve — pra ter acesso a produtos de dados é preciso
ser **associado** ou ter contrato comercial. Pivotamos para os arquivos
públicos de `www.anbima.com.br/informacoes/*`, que entregam os mesmos
números canônicos sem nenhum gating.

A integração pela API autenticada **pode voltar como camada opcional**
no futuro pra dados em near-real-time, mas ANBIMA nunca vai ser
exclusivamente auth-walled — é uma fonte do core, ponto.

## Fonte de exemplo: ANBIMA via API autenticada (como seria)

Se algum contribuidor com entitlement quiser implementar:

**Como obter credenciais:**

1. Cadastre-se em <https://developers.anbima.com.br>
2. Crie um app
3. Subscreva ele aos produtos (Preços e Índices, etc.)
4. Pegue o `client_id` e `client_secret`

**Configurar:**

```bash
export ANBIMA_CLIENT_ID="seu-client-id"
export ANBIMA_CLIENT_SECRET="seu-client-secret"
```

Quirks da API ANBIMA (já validamos em testes ao vivo):

- Token endpoint: `POST /oauth/access-token` (não `/oauth/token`).
- Header de auth: `access_token: <token>` (não `Authorization: Bearer`).
- Header obrigatório adicional: `client_id: <client_id>`.
- `403 "Access denied for this environment"` → seu app não está
  subscrito ao produto.



## Base dos Dados: grátis, mas com login/projeto do usuário

Base dos Dados não entra na mesma categoria da API autenticada da ANBIMA. O
acesso via SQL, Python e R é gratuito, mas costuma exigir login Google e um
projeto BigQuery do próprio operador. No `findata-br`, classifique esse caminho
como `free_logged_in`: gratuito e self-serve, porém não anônimo/zero-setup.

Datasets e funcionalidades BD Pro devem ficar marcados separadamente como
`paid_logged_in` e nunca como requisito para a fonte gratuita.

Para consultas BigQuery locais, use o extra opcional e um projeto de billing do
próprio operador:

```bash
pip install 'findata-br[basedosdados]'
export FINDATA_BD_BILLING_PROJECT_ID="seu-projeto-gcp"
findata basedosdados query 'SELECT * FROM `basedosdados.br_bd_diretorios_brasil.municipio` LIMIT 5'
```

O projeto também aceita `BASE_DOS_DADOS_BILLING_PROJECT_ID` ou
`GOOGLE_CLOUD_PROJECT`. Não embuta credenciais Google nem billing project nos
testes, docs de exemplo reais ou artefatos versionados.

## Open Finance Brasil: somente recursos públicos neste projeto

A integração `openfinance` do findata-br é deliberadamente o Track A: Diretório
público, JWKS públicos, `.well-known`, recursos publicados e Portal de Dados.
Ela não usa API key, certificado privado, token, DCR, consentimento ou mTLS do
operador.

Conectar com bancos para solicitar dados cadastrais/transacionais de clientes é
outro caso: exige onboarding institucional, certificados ICP-Brasil, segurança
FAPI/RP, registro no Diretório, consentimento e certificação. Se isso entrar no
roadmap, deve ficar como módulo opcional e isolado, não como fonte pública core.

## Fontes futuras candidatas

| Fonte | Tipo | Trigger pra implementar |
|---|---|---|
| **SUSEP** | OAuth2 (provável) | Issue ou PR da comunidade |
| **BNDES Open Banking** | API key | Issue ou PR |
| **CETIP / B3 Balcão** | API key + IP whitelist | Sob demanda |

Cada nova fonte segue o mesmo padrão: módulo em `findata/sources/<fonte>/`,
router em `findata/api/routers/<fonte>.py`, env vars apropriadas,
comportamento `503 → 401 → success` consistente.

## Como adicionar uma nova fonte com auth

1. **`src/findata/sources/<fonte>/credentials.py`** — função
   `load_<fonte>_credentials()` que lê env vars e levanta
   `MissingCredentialsError` quando ausentes.
2. **`src/findata/sources/<fonte>/client.py`** — subclasse de
   `OAuth2ClientCredentials` (em `findata.auth.oauth2`) com
   `_token_url`, `header_name` e `header_prefix` certos pro provider.
3. **`src/findata/api/routers/<fonte>.py`** — router FastAPI usando
   um helper `_safely` que traduz `MissingCredentialsError` → 503,
   `AuthError` → 502, `httpx.HTTPStatusError` → upstream code.
4. **`tests/test_<fonte>.py`** — testes mockados via `respx` que
   verificam 503 quando creds ausentes + happy path com env vars
   setadas.
5. **PR com link pro developer portal** do provedor pra reviewers
   conferirem o ToS.

O framework `findata.auth` está intocado e pronto — `OAuth2Token`,
`OAuth2ClientCredentials` (com cache + safety margin), `AuthError` e
`MissingCredentialsError`. Veja `tests/test_auth.py` pra exemplos.
