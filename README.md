# Zeus

Agent harness minimalista escrito em Python. Agente = modelo + harness. Zeus é o harness: loop ReAct, registro de ferramentas, roteamento de modelos, memória persistente, sandbox isolada, observabilidade e execução em background.

## Estrutura

```
zeus/
├── core/           # agent loop, registry, router, multi-agent team
├── tools/          # 29 ferramentas disponíveis
├── memory/         # memória persistente (JSON + SQLite)
├── db/             # SQLite: memories, sessions, turns, metrics, scheduled_tasks
├── observability/  # métricas, custo, tracing, reporter
├── scheduler/      # thread polling para tarefas cron
├── gateway/        # Telegram, WhatsApp, Discord
└── cli/            # interface interativa
```

## Instalação

```bash
cd /home/vps28/Documentos/Dev/Zeus
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# (opcional) compilar sandbox Go
cd sandbox && go build -o sandbox ./cmd/sandbox && cd ..
```

## Configuração

Crie `.env` na raiz do projeto ou use `~/.zeus/.env`. Você pode gerenciar variáveis via CLI:

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
# Modo interativo
python -m zeus.cli

# Query única
python -m zeus.cli -q "liste arquivos do diretório atual"

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

29 ferramentas em 7 categorias: sistema, arquivos, web, memória, git, código, browser, banco de dados, scheduler. Veja `docs/TOOLS.md`.

## Gateways

Telegram, WhatsApp e Discord. Veja `docs/GATEWAY.md`.

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

Código shell/python executado em ambiente isolado com chroot, namespaces, cgroups, seccomp-bpf e drop para `nobody`. Start:

```bash
sudo ./sandbox/sandbox -addr 127.0.0.1:9876
```

## Documentação

- `docs/ARCHITECTURE.md` — arquitetura detalhada
- `docs/USAGE.md` — uso completo
- `docs/TOOLS.md` — todas as 29 ferramentas
- `docs/SANDBOX.md` — detalhes da sandbox
- `docs/MCP.md` — Model Context Protocol
- `docs/CONFIG.md` — gerenciamento de configurações
- `docs/LEARNING.md` — aprendizado contínuo
