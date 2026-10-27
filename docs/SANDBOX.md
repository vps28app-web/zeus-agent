# Sandbox Go do Zeus

A sandbox é um servidor HTTP em Go; o harness Python envia comandos para ele. O endpoint de execução aceita apenas requisições locais e não tem fallback para execução no host.

## Requisitos de execução

- Linux x86_64 (amd64) e Go 1.20 ou superior para compilar.
- Servidor iniciado como root.
- cgroup v2 com os controladores `cpu`, `memory` e `pids` disponíveis e habilitados; os grupos de execução também precisam oferecer `cgroup.kill`.
- Permissões de kernel para mount namespaces, chroot e seccomp-bpf.

Se um desses mecanismos obrigatórios não puder ser aplicado, o Zeus recusa o comando. Não use `sudoers` com `NOPASSWD` amplo para este binário; prefira o serviço systemd fornecido e restrinja quem pode controlá-lo.

## Compilar

```bash
cd /caminho/para/Zeus/sandbox
go build -o sandbox ./cmd/sandbox
```

O servidor rejeita endereços que não sejam IPs de loopback literais. Para acesso remoto, mantenha-o no loopback e use um proxy reverso com TLS e autenticação.

O token bearer é obrigatório: o servidor se recusa a iniciar sem `ZEUS_SANDBOX_AUTH_TOKEN`. Configure o mesmo valor no ambiente do serviço e do processo Zeus. Para iniciar manualmente:

```bash
export ZEUS_SANDBOX_AUTH_TOKEN="$(openssl rand -hex 32)"
# Configure esse mesmo valor no .env do Zeus.
sudo -E ./sandbox -addr 127.0.0.1:9876
```

O serviço systemd fornecido executa a cópia root-owned em `/usr/local/lib/zeus/sandbox` e lê `ZEUS_SANDBOX_AUTH_TOKEN` de `/etc/zeus/sandbox.env`. `scripts/install-systemd.sh` instala o binário protegido e copia somente o token para o arquivo, com permissões `600`; o mesmo valor permanece no `.env` do Zeus. Para instalação manual, configure um `EnvironmentFile` protegido ou um drop-in com `systemctl edit`; nunca publique o token.

## API e limites

- `GET /health`
- `POST /run` — JSON: `{ "command": "echo hello", "timeout_sec": 30, "memory_mb": 128, "cpu_pct": 50 }`

Limites máximos por execução: 300 segundos, 4096 MiB, 100% de CPU e 256 processos. Os valores zero selecionam os padrões (30 segundos, 128 MiB, 50% e 64 processos). A saída é limitada a 512 KiB por stream; no máximo quatro comandos rodam simultaneamente. O corpo HTTP é limitado a 64 KiB.

`work_dir` não é aceito: cada execução recebe um diretório temporário privado, removido ao terminar. Transferência de arquivos ainda não está implementada.

## Fronteiras de isolamento

- Mount, PID, network, IPC e UTS namespaces.
- Mount namespace privado obrigatório; falha em torná-lo privado interrompe a execução.
- Chroot em tmpfs; `/etc` do host não é montado. Binários e bibliotecas são montados read-only, `nosuid` e `nodev`.
- O payload perde grupos suplementares e roda como `nobody`.
- Seccomp-bpf é obrigatório, falha fechada e, nesta versão, só aceita amd64.
- cgroups v2 por execução aplicam memória, quota de CPU e limite de PIDs; processos restantes são encerrados no cleanup.
- A allowlist valida a sintaxe shell como camada adicional, mas não substitui as barreiras do kernel.

A sandbox reduz o risco, mas não é uma barreira absoluta contra vulnerabilidades do kernel. Execute o daemon apenas em máquinas confiáveis e mantenha o kernel atualizado.

## Verificação

`go test ./...` cobre a lógica de validação, filtros, limites e handlers. Isso não substitui testes de integração privilegiados no host de implantação: antes de produção, valide mount/chroot/seccomp/cgroups com root em Linux amd64 e confirme que o serviço recusa execução quando qualquer requisito falta.
