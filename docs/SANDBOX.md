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

Privilégios de root são obrigatórios para executar comandos. Sem root, o servidor pode iniciar e responder a `GET /health`, mas recusa `POST /run`; executar payloads no host sem chroot não é considerado um modo sandbox seguro.

### Opção 1: com sudo (hardening completo)

```bash
sudo ./sandbox -addr 127.0.0.1:9876
```

Para rodar sem digitar senha, crie `/etc/sudoers.d/zeus-sandbox`:

```sudoers
vps28 ALL=(root) NOPASSWD: /home/vps28/Documentos/Dev/Zeus/sandbox/sandbox
```

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

- `echo hello && whoami && pwd && ls /` — executa dentro do chroot; o payload roda como `nobody`.
- `curl http://example.com` — bloqueado (sem rede).
- `rm -rf /tmp/...` — executa dentro do tmpfs isolado.
- `cat /etc/passwd` — vê apenas a cópia read-only dentro do chroot.

## Notas de segurança

- Root é obrigatório para executar; sem root, `POST /run` é recusado.
- A allowlist usa AST shell para validar cada comando explícito em pipes/listas e rejeita nomes dinâmicos e caminhos de executáveis.
- A allowlist é uma camada adicional: binários permitidos ainda podem iniciar subprocessos; chroot/namespaces/seccomp são a fronteira principal.
- O payload roda como `nobody` no chroot. Ainda existe risco de vulnerabilidade do kernel; a sandbox não é uma barreira absoluta.

## Próximos passos

1. Tornar a instalação de seccomp obrigatória (hoje uma falha é registrada e a execução continua).
2. Suporte a upload/download de arquivos na sandbox.
3. Empacotar como serviço systemd.
