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

## Endpoints

- `GET /health`
- `POST /run` — payload JSON: `{ "command": "...", "timeout_sec": 30, "memory_mb": 128, "cpu_pct": 50 }`

## Notas de segurança

- A sandbox não é uma barreira de segurança absoluta sem root.
- Comandos ainda executam como o usuário do processo quando não há chroot.
- Sempre revise comandos antes de executar em produção.
