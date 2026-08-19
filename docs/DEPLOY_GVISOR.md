# FastAPI interno com gVisor (VPS + Tailscale)

O processo Python **não é a superfície pública**. MCP público:
[`DEPLOY_WORKERS_MCP.md`](DEPLOY_WORKERS_MCP.md).

Este guia sobe o FastAPI em VPS com runtime **runsc (gVisor)**,
publicado só em loopback e no IP Tailscale — sem Traefik, sem 80/443
para este serviço.

> Esta VPS **não tem KVM aninhado**. O gVisor em modo **systrap** é a camada de
> sandbox do processo do container, **não** uma segunda VM.

## Pré-requisitos

- Docker Engine com runtime **runsc** instalado
- IP Tailscale da VPS (compose usa `TAILSCALE_IP`, default `100.90.45.18`)

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
export TAILSCALE_IP=$(tailscale ip -4)
python3 deploy/assert_tailscale_bind.py   # recusa 0.0.0.0 / IPs fora de 100.64.0.0/10
cd /opt/openfindata
docker compose -f deploy/docker-compose.gvisor.yml up -d --build
```

O compose publica em `127.0.0.1:8000` e no IP Tailscale. **Sem** labels
Traefik. **Não** anexe esta rede a stacks hermes/wealthuman. **Não** habilite
code mode (`FINDATA_MCP_CODE_MODE` fica `"0"` neste compose).


## Smoke checks (Tailscale / loopback)

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/stats
curl -sS 'http://127.0.0.1:8000/bcb/series/name/selic?n=3'
# from a Tailscale peer:
curl -sS "http://${TAILSCALE_IP:-100.90.45.18}:8000/health"
```

Público (Worker, não esta VPS): ver [`DEPLOY_WORKERS_MCP.md`](DEPLOY_WORKERS_MCP.md).

## Checklist de segurança

- [ ] `runtime: runsc` ativo no container
- [ ] publish em loopback + IP Tailscale (não 0.0.0.0, sem Traefik)
- [ ] sem mount de `docker.sock`
- [ ] sem `network_mode: host`
- [ ] `python3 deploy/assert_tailscale_bind.py` passou
- [ ] code mode desligado (`FINDATA_MCP_CODE_MODE=0` neste compose)
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

Se o FastAPI não responder na Tailscale, confira `TAILSCALE_IP`, `ufw` (não
expor 8000 na internet) e se o container ainda tem labels Traefik (não deve).
