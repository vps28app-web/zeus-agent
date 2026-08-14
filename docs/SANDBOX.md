# Sandbox Go do Zeus

## Visão geral

A sandbox é um servidor HTTP escrito em Go que executa comandos shell em processos isolados. O harness Python se comunica com ela via HTTP.

## Estrutura

```
sandbox/
├── cmd/sandbox/main.go     # entry point do servidor
├── internal/server/server.go # handlers HTTP
└── internal/runner/runner.go # execução isolada
```

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

Para rodar sem digitar senha, crie `/etc/sudoers.d/zeus-sandbox`:

```sudoers
vps28 ALL=(root) NOPASSWD: /home/vps28/Documentos/Dev/Zeus/sandbox/sandbox
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

## Uso pelo Zeus

A ferramenta `run_sandboxed` está disponível no agente. Exemplo:

```bash
python -m zeus.cli -q "execute run_sandboxed with command 'echo hello from sandbox'"
```

## Isolamento atual (com root)

- **chroot** em tmpfs com binários essenciais montados read-only.
- **Namespaces**: mount, PID, network, IPC, UTS.
- **cgroups v2**: limites de memória e peso de CPU.
- **rede bloqueada** por padrão (CLONE_NEWNET sem configuração de interface).
- ambiente limpo sem variáveis do host.

## Testes validados

- `echo hello && whoami && pwd && ls /` — executa dentro do chroot como root.
- `curl http://example.com` — bloqueado (sem rede).
- `rm -rf /tmp/...` — executa dentro do tmpfs isolado.
- `cat /etc/passwd` — vê apenas a cópia read-only dentro do chroot.

## Notas de segurança

- A sandbox não é uma barreira absoluta, mas reduz bastante a superfície de ataque.
- Comandos dentro do chroot rodam como root — ainda há risco de kernel exploits.
- Para uso em produção, considere usuário não-root dentro do container ou VM.

## Próximos passos

1. Rodar o comando final dentro do chroot como usuário não-root.
2. Adicionar seccomp-bpf para bloquear syscalls perigosas.
3. Suporte a upload/download de arquivos na sandbox.
4. Empacotar como serviço systemd.
