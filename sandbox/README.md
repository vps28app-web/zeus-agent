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

### Sem root

O servidor pode iniciar sem root, mas qualquer pedido a `POST /run` é recusado com erro explícito. O Zeus não executa o comando no host sem chroot; o modo parcial anterior não fornecia isolamento de arquivos suficiente para ser seguro.

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

- **Allowlist de comandos**: AST shell valida cada comando explícito em pipes/listas e rejeita nomes dinâmicos e caminhos de executáveis. É uma camada extra, não substitui namespaces/chroot/seccomp; binários permitidos ainda podem iniciar subprocessos.
- **Sem root**: `POST /run` é recusado; o comando não é executado no host sem chroot.
- Mesmo com root, a sandbox não é uma barreira absoluta contra vulnerabilidades do kernel; o payload roda como `nobody` dentro do chroot.
- A interface HTTP escuta apenas em `127.0.0.1` por padrão; não exponha para redes externas.
- Habilite `ZEUS_SANDBOX_AUTH_TOKEN` para restringir acesso local.
- O endpoint `/run` tem rate limit de 60 requisições/minuto por IP.
- Sempre revise comandos antes de executar em produção.
