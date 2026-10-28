# Zeus

Agent harness minimalista escrito em Python. Agente = modelo + harness. Zeus é o harness: loop ReAct, registro de ferramentas, roteamento de modelos, memória persistente, sandbox isolada, observabilidade e execução em background.

## Estrutura

```
zeus/
├── core/           # agent loop, registry, router, multi-agent team
├── tools/          # ferramentas nativas
├── memory/         # memória persistente (JSON + SQLite)
├── db/             # SQLite: memories, sessions, turns, metrics, scheduled_tasks
├── observability/  # métricas, custo, tracing, reporter
├── scheduler/      # thread polling para tarefas cron
├── gateway/        # Telegram, WhatsApp, Discord
└── cli/            # interface interativa
```

## Instalação

Em Linux/macOS com Python 3.8+ e Git, clone o repositório e execute o instalador sem `sudo`:

```bash
git clone https://github.com/vps28app-web/zeus-agent.git
cd zeus-agent
./scripts/install.sh
zeus setup
```

O instalador cria `.venv`, instala o pacote e os comandos `zeus`/`zeus-gateway`, cria a configuração privada em `~/.zeus/.env` e gera o token da sandbox. Em Linux amd64, se Go estiver disponível, também compila a sandbox opcional. Detalhes e alternativas: [`docs/INSTALACAO.md`](docs/INSTALACAO.md).

## Configuração

A instalação recomendada cria e usa `~/.zeus/.env`; também é possível definir outro `ZEUS_HOME` absoluto. Para instalações antigas, o Zeus ainda pode ler um `.env` na raiz do projeto. Gerencie as variáveis via CLI:

```bash
# Ver configuração atual
/config

# Definir provider/modelo em tempo real
/config set ZEUS_PROVIDER openrouter
/config set ZEUS_MODEL openrouter/auto

# Listar modelos de um provider
/config list-models google
```

Exemplo de `.env`:

```bash
# Provedor
ZEUS_PROVIDER=opencode_go
ZEUS_MODEL=kimi-k2.7-code

# API keys
OPENCODE_GO_API_KEY=sk-...
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-...
# GOOGLE_API_KEY=...
# DEEPSEEK_API_KEY=sk-...
# MISTRAL_API_KEY=...

# Sandbox (se usar ferramentas de código isolado)
ZEUS_SANDBOX_URL=http://127.0.0.1:9876
```

## Model Context Protocol (MCP)

O Zeus pode se conectar a servidores MCP externos para expandir suas ferramentas:

```bash
# No CLI interativo
/mcp add gemini
/mcp add filesystem
/mcp add memory
/mcp list
/mcp reload
```

Ferramentas MCP são registradas automaticamente no agente com o prefixo `mcp_<servidor>_`.

## Uso rápido

```bash
# Configuração inicial interativa (provedor/modelo + integrações escolhidas)
zeus setup

# Modo interativo
python -m zeus.cli

# Query única
python -m zeus.cli -q "liste arquivos do diretório atual"
```

No CLI local, você pode trocar de projeto pedindo ao Zeus, por exemplo: “mude a pasta de trabalho para /caminho/do/projeto”. A mudança vale até encerrar o processo e também ajusta a fronteira de acesso do modo `project_only`; não altera arquivos de configuração.

```bash
# Comandos interativos úteis
/help       # menu de comandos
/skills     # selecionar persona
/config     # ver configurações
/config set ZEUS_PROVIDER openai
/mcp add gemini
/models     # trocar modelo/provedor
/learn      # aprendizados passados
/plan       # criar e executar plano
/team       # equipe multi-agente
```

## Ferramentas

50 ferramentas em 8 categorias: sistema, arquivos, web, memória, aprendizado, git, scheduler e configuração. Veja `docs/TOOLS.md`.

## Gateways

Telegram, WhatsApp, Discord e Instagram Messaging (conta Profissional via API oficial da Meta). Veja `docs/GATEWAY.md`.

## Tarefas agendadas

```python
from zeus.tools.scheduler import schedule_task

schedule_task(
    command="ls -la /tmp",
    schedule="0 9 * * *",  # todo dia às 9h
    description="listar /tmp"
)
```

## Sandbox Go

A sandbox requer Linux x86_64, Go 1.20+, root e cgroup v2 com `cpu`, `memory` e `pids` habilitados, além de mount namespaces e seccomp-bpf. Ela falha fechada se não puder aplicar esses controles e só escuta em loopback. Veja `docs/SANDBOX.md` para requisitos, limites e implantação.

Para instalação persistente, use o instalador systemd documentado em [`docs/INSTALACAO.md`](docs/INSTALACAO.md). Ele copia a sandbox para uma localização root-owned; execute-o apenas com uma revisão confiável e limpa do Git. Evite iniciar manualmente como root um binário dentro do checkout editável.

## Documentação

- `docs/PROJETO.md` — visão geral e arquitetura de alto nível
- `docs/INSTALACAO.md` — instalação local e systemd passo a passo
- `docs/ARCHITECTURE.md` — componentes internos
- `docs/USAGE.md` — uso completo
- `docs/TOOLS.md` — todas as 50 ferramentas
- `docs/GATEWAY.md` — gateways Telegram, WhatsApp, Discord e Instagram Messaging
- `docs/SANDBOX.md` — detalhes da sandbox
- `docs/MCP.md` — Model Context Protocol
- `docs/CONFIG.md` — gerenciamento de configurações
- `docs/LEARNING.md` — aprendizado contínuo

## Autor

- **vps28**

