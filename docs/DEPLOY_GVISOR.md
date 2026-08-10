# Deploy público com gVisor (VPS)

Guia prático para subir o **Dados Financeiros Abertos** em VPS com runtime
**runsc (gVisor)**, Traefik em host mode e rede isolada.

> Esta VPS **não tem KVM aninhado**. O gVisor em modo **systrap** é a camada de
> sandbox do processo do container, **não** uma segunda VM.

## Pré-requisitos

- Docker Engine com runtime **runsc** instalado
- Traefik já em host mode na monvanti-vps (entrypoints `websecure`, certresolver
  `letsencrypt`)
- Domínio apontando para a VPS

### Instalar gVisor / runsc (snippet)

```bash
# Exemplo baseado em release oficial do gVisor (ajuste a arquitetura se preciso)
ARCH=$(uname -m)
URL=https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}
curl -fsSL "${URL}/runsc" -o /tmp/runsc
curl -fsSL "${URL}/runsc.sha512" -o /tmp/runsc.sha512
(cd /tmp && sha512sum -c runsc.sha512)
sudo mv /tmp/runsc /usr/local/bin/runsc
sudo chmod 755 /usr/local/bin/runsc

# Registrar o runtime sem sobrescrever o daemon.json existente
sudo /usr/local/bin/runsc install
sudo systemctl reload docker || sudo systemctl restart docker
```

Verifique:

```bash
docker info | grep -i runsc
docker run --rm --runtime=runsc hello-world
```

## Clone / update em `/opt/openfindata`

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/robertoecf/openfindata.git /opt/openfindata
# ou, se já existir:
cd /opt/openfindata && sudo git pull --ff-only
cd /opt/openfindata
```

## Variável de host

```bash
export OPENFINDATA_HOST=seu.dominio
# opcional: persistir em deploy/.env ao lado do compose
```

## Subir o serviço

```bash
cd /opt/openfindata
docker compose -f deploy/docker-compose.gvisor.yml up -d --build
```

O compose publica só em `127.0.0.1:8000` e usa labels Traefik. **Não** anexe esta
rede a stacks hermes/wealthuman. **Não** habilite code mode
(`FINDATA_MCP_CODE_MODE` deve permanecer ausente).


## Traefik host mode + health

Traefik on this VPS uses `network_mode: host`. Point the service at the published
loopback port:

```yaml
traefik.http.services.openfindata.loadbalancer.server.url=http://127.0.0.1:8000
```

Do **not** set `traefik.docker.network=...` for this layout.

Traefik v3 **drops routers for Docker-unhealthy containers**. If `/health` is rate
limited, the container goes unhealthy and public HTTPS returns Traefik
`404 page not found` even while `curl 127.0.0.1:8000/health` still works.
`/health` is rate-limit exempt for that reason.

## Smoke checks

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/stats
curl -sS 'http://127.0.0.1:8000/bcb/series/name/selic?n=3'
# MCP HTTP transport:
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/mcp
```

Pelo domínio (via Traefik):

```bash
curl -sS "https://${OPENFINDATA_HOST}/health"
curl -sS "https://${OPENFINDATA_HOST}/stats"
curl -sS "https://${OPENFINDATA_HOST}/bcb/series/name/selic?n=3"
```

## Checklist de segurança

- [ ] `runtime: runsc` ativo no container
- [ ] publish apenas em loopback (`127.0.0.1:8000`)
- [ ] sem mount de `docker.sock`
- [ ] sem `network_mode: host`
- [ ] code mode desligado (sem `FINDATA_MCP_CODE_MODE`)
- [ ] rede isolada `openfindata_net` (não compartilhada com hermes/wealthuman)
- [ ] limite de memória (`mem_limit: 512m`) e CPU (`cpus: 1.0`)
- [ ] `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges:true`
- [ ] DNS via `deploy/resolv.gvisor.conf` (gVisor + `127.0.0.11` falha)

## Troubleshooting

```bash
# runtime registrado?
docker info | grep -i runsc

# runtime executa?
docker run --rm --runtime=runsc hello-world

# container e health
docker compose -f deploy/docker-compose.gvisor.yml ps
docker inspect --format '{{.HostConfig.Runtime}}' openfindata
curl -v http://127.0.0.1:8000/health
```

Se o Traefik não rotear, confira `OPENFINDATA_HOST`, se o Traefik enxerga a rede
do container e se o entrypoint `websecure` + `letsencrypt` já estão válidos na
monvanti-vps.
