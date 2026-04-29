# Open Finance Brasil: recursos públicos

Este projeto implementa apenas o **Track A** do Open Finance Brasil: dados
públicos de descoberta, diretório e indicadores agregados. Não há conexão com
contas de cliente, consentimento, mTLS privado, DCR ou credenciais no repositório.

## Escopo implementado

### Diretório público

Base de produção:

- `https://data.directory.openbankingbrasil.org.br/participants`
- `https://data.directory.openbankingbrasil.org.br/roles`
- `https://web.directory.openbankingbrasil.org.br/config/apiresources`
- `https://auth.directory.openbankingbrasil.org.br/.well-known/openid-configuration`
- `https://keystore.directory.openbankingbrasil.org.br`

Também há suporte ao ambiente `sandbox` via `environment=sandbox` na API ou
`--env sandbox` na CLI.

### Chaves públicas do diretório

O adaptador também expõe os endpoints públicos parametrizados de JWKS:

- `/{organisationId}/application.jwks`
- `/{organisationId}/{softwareStatementId}/transport.jwks`
- `/{organisationId}/{softwareStatementId}/application.jwks`

Esses recursos são apenas de consulta pública. Eles não substituem cadastro,
certificados próprios ou certificação de participante.

### Portal de Dados

O catálogo cobre os 10 conjuntos públicos do Portal de Dados do Open Finance:

- Chamadas por APIs - Dados Abertos
- Chamadas por APIs - Dados do Cliente
- Chamadas por APIs - Serviços
- Consentimentos Ativos
- Consentimentos Únicos
- Funil de Consentimentos
- Funil de Pagamentos
- Ranking - Dados Abertos
- Ranking - Dados do Cliente
- Ranking - Serviços

O parser lista arquivos públicos de download por página do dataset e baixa o
arquivo bruto por `download_id`, sem cachear o payload e com limite de 20 MB
por download para proteger o processo.

## API REST

```bash
curl http://localhost:8000/openfinance/resources
curl 'http://localhost:8000/openfinance/participants?role=DADOS&limit=20'
curl 'http://localhost:8000/openfinance/endpoints?api_family=channels&limit=20'
curl http://localhost:8000/openfinance/directory/roles
curl http://localhost:8000/openfinance/directory/api-resources
curl http://localhost:8000/openfinance/directory/well-known
curl http://localhost:8000/openfinance/directory/keystore
curl http://localhost:8000/openfinance/portal/datasets
curl http://localhost:8000/openfinance/portal/datasets/chamadas-por-apis-dados-abertos/files
```

## CLI

```bash
findata openfinance resources
findata openfinance participants --role DADOS -n 20
findata openfinance endpoints --api-family channels -n 20
findata openfinance datasets
findata openfinance files chamadas-por-apis-dados-abertos
```

## Guardrail: o que fica fora

Ficam fora deste módulo:

- acesso a dados cadastrais/transacionais de cliente;
- criação de consentimento;
- iniciação de pagamento;
- registro dinâmico de cliente;
- mTLS com certificados privados do operador;
- assinatura `private_key_jwt`;
- certificação FAPI/RP/OIDF;
- armazenamento de chaves, tokens ou secrets.

Se esse escopo for necessário, trate como um produto separado e regulado, não
como uma fonte pública comum do `findata-br`.
