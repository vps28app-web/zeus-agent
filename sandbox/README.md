# Zeus Sandbox

Runtime de execução isolada escrito em Go para o agent harness Zeus.

## Compilar

```bash
cd /home/vps28/Documentos/Dev/Zeus/sandbox
go build -buildvcs=false ./cmd/sandbox
```

## Executar

O modo hardening completo (chroot, mount namespace, network namespace, cgroups) requer privilégios de root.

### Opção 1: com sudo (hardening completo)

```bash
sudo ./sandbox -addr 127.0.0.1:9876
```

### Opção 2: sem root (isolamento parcial)

Sem root o servidor funciona, mas o chroot e o mount namespace privado falham. Ainda há:

- diretório de trabalho temporário
- ambiente limpo
- timeout
- limitação via cgroups (se disponível e permissível)

### Autenticação (recomendado)

Configure um token compartilhado entre o Zeus e o sandbox para evitar que outros usuários/processos locais enviem comandos:

```bash
export ZEUS_SANDBOX_AUTH_TOKEN="$(openssl rand -hex 32)"
sudo -E ./sandbox -addr 127.0.0.1:9876
```

O Zeus envia o token automaticamente quando a variável está definida.

## Endpoints

- `GET /health`
- `POST /run` — payload JSON: `{ "command": "...", "timeout_sec": 30, "memory_mb": 128, "cpu_pct": 50 }`

## Notas de segurança

- A sandbox não é uma barreira de segurança absoluta sem root.
- Comandos ainda executam como o usuário do processo quando não há chroot.
- A interface HTTP escuta apenas em `127.0.0.1` por padrão; não exponha para redes externas.
- Habilite `ZEUS_SANDBOX_AUTH_TOKEN` para restringir acesso local.
- O endpoint `/run` tem rate limit de 60 requisições/minuto por IP.
- Sempre revise comandos antes de executar em produção.
