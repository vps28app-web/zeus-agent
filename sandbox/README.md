# Zeus Sandbox

Implementação Go do runtime de execução isolada. Requisitos, limites, isolamento, API e procedimentos de implantação ficam documentados em [`../docs/SANDBOX.md`](../docs/SANDBOX.md).

Resumo: Linux amd64, Go 1.20+, root, cgroup v2 com `cpu`, `memory` e `pids` habilitados, além de mount namespaces e seccomp-bpf. A sandbox falha fechada se não conseguir aplicar os controles obrigatórios; não executa o comando no host como fallback.

Build e execução local (o token precisa estar configurado também no ambiente do Zeus):

```bash
go build -o sandbox ./cmd/sandbox
export ZEUS_SANDBOX_AUTH_TOKEN="$(openssl rand -hex 32)"
sudo -E ./sandbox -addr 127.0.0.1:9876
```

O servidor só aceita bind em loopback. Não o exponha diretamente à rede; use proxy reverso com TLS e autenticação para acesso remoto.
