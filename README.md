# Zeus

Agent harness minimalista escrito em Python. **Agente = modelo + harness.**  
O Zeus fornece o harness completo: loop ReAct, registro de ferramentas, roteamento de modelos, memória persistente, sandbox isolada, observabilidade e execução em background.

O projeto oferece duas interfaces sobre o mesmo core:
- **Zeus CLI** — interface interativa no terminal, modo *single-query*, gateways e automações.
- **Zeus Desktop** — cliente gráfico nativo em Rust (`eframe`/`egui`) integrado ao core Python via bridge JSONL.

---

## Estrutura

```text
zeus/
├── core/           # agent loop, registry, router, multi-agent team
├── tools/          # ferramentas nativas
├── memory/         # memória persistente (JSON + SQLite)
├── db/             # SQLite: memories, sessions, turns, metrics, scheduled_tasks
├── observability/  # métricas, custo, tracing, reporter
├── scheduler/      # thread polling para tarefas cron
├── gateway/        # Telegram, WhatsApp, Discord e Instagram Messaging
└── cli/            # interface interativa e bridge JSONL (--desktop-json)

desktop/            # cliente gráfico nativo em Rust (eframe/egui)
scripts/            # instaladores locais, Zeus Desktop e serviços systemd
docs/               # documentação detalhada do projeto
```

---

## Instalação

### 1. Zeus CLI (Core)

Em Linux/macOS com Python 3.8+ e Git, clone o repositório e execute o instalador sem `sudo`:

```bash
git clone https://github.com/vps28app-web/zeus-agent.git
cd zeus-agent
./scripts/install.sh
zeus setup
```

O instalador cria `.venv`, instala o pacote e os comandos `zeus` e `zeus-gateway`, cria a configuração privada em `~/.zeus/.env` e gera o token da sandbox. Em Linux amd64, se Go estiver disponível, também compila a sandbox opcional. Detalhes e alternativas em [`docs/INSTALACAO.md`](docs/INSTALACAO.md).

### 2. Zeus Desktop (Rust Nativo)

Para instalar o cliente gráfico nativo ([`desktop/README.md`](desktop/README.md)) sem `sudo` (requer `cargo`/Rust para compilar, ou `--no-build` se o binário release já existir):

```bash
./scripts/install-desktop.sh
# ou via npm (na raiz do repositório):
npm run install:desktop
```

O instalador verifica automaticamente a base Python do Zeus Core (`.venv`, comandos e `~/.zeus/.env`), executando `./scripts/install.sh` quando necessário, compila o binário release e registra `~/.local/bin/zeus-desktop`, o atalho `.desktop` e o ícone SVG no menu de aplicativos.

Opções úteis:
- `./scripts/install-desktop.sh --no-build` — usa o binário em `desktop/target/release/zeus-desktop` sem recompilar
- `./scripts/install-desktop.sh --with-core` — força a reinstalação/atualização do Zeus Core antes do Desktop
- `./scripts/install-desktop.sh --skip-core` — instala apenas o binário Desktop sem validar o Zeus Core
- `./scripts/uninstall-desktop.sh` — remove o cliente Desktop (adicione `--state` para apagar também `~/.zeus/desktop-state.json`)

### 3. Comando global e instalador via npm

#### Expor `zeus` e `zeus-gateway` globalmente

Depois de instalar o core (por qualquer fluxo), exponha os comandos para uso em qualquer diretório (requer Node.js 18+):

```bash
npm install -g git+https://github.com/vps28app-web/zeus-agent.git
# ou, dentro de um checkout:
npm install -g .

zeus --version
```

O launcher localiza a instalação existente (`ZEUS_INSTALL_DIR`, checkout acima do diretório atual, registro `~/.zeus/install-dir` ou `~/.local/share/zeus-agent`) e executa o Zeus preservando o diretório atual como workspace.

#### Instalação completa em Debian/Ubuntu amd64 via `npx`

Em Debian/Ubuntu amd64 com Go 1.20+ disponível nos repositórios `apt`, é possível preparar as dependências e instalar/iniciar a sandbox `systemd` em uma execução, sem clonar manualmente:

```bash
npx --yes --package=git+https://github.com/vps28app-web/zeus-agent.git zeus-install
```

Dentro de um checkout existente, o equivalente é `npm run install:zeus` (exige `package.json` no diretório atual). O instalador solicita confirmação antes de instalar pacotes de sistema e pedir autorização administrativa para o serviço da sandbox.

Para remover: use `zeus-uninstall` (de qualquer diretório) ou `./scripts/uninstall.sh` no checkout, e `npm uninstall -g zeus-agent-installer` para remover os comandos globais. Mais detalhes em [`docs/INSTALACAO.md`](docs/INSTALACAO.md).

---

## Uso

### Zeus CLI

```bash
# Configuração inicial interativa (provedor/modelo + integrações)
zeus setup

# Modo interativo
zeus
# ou: python -m zeus.cli

# Query única
zeus -q "liste arquivos do diretório atual"
```

Comandos interativos úteis no CLI:

```text
/help       # menu de comandos
/skills     # selecionar persona
/config     # ver/alterar configurações
/models     # trocar modelo/provedor
/mcp        # gerenciar servidores MCP
/learn      # aprendizados passados
/plan       # criar e executar plano
/team       # equipe multi-agente
```

No CLI local, você também pode trocar de projeto em tempo de execução pedindo ao Zeus (ex.: *"mude a pasta de trabalho para /caminho/do/projeto"*), ajustando a fronteira do modo `project_only` até encerrar o processo sem alterar arquivos de configuração.

### Zeus Desktop

Após instalar, execute `zeus-desktop` no terminal ou abra **Zeus Desktop** pelo menu de aplicativos.

O cliente em `desktop/` comunica-se com o harness Python via JSONL (`zeus --desktop-json` e `zeus --desktop-catalog`) e oferece:
- Chat em streaming com renderização Markdown e blocos recolhíveis de *reasoning* e *tool calls*
- Aprovações interativas *Human-in-the-Loop* para ferramentas sensíveis
- Seleção dinâmica de provedor, modelo e esforço de raciocínio (`ZEUS_REASONING_EFFORT`)
- Gerenciamento visual de chaves em `~/.zeus/.env` e servidores MCP
- Painel lateral com histórico de sessões, métricas de observabilidade, tarefas agendadas e memória persistente

Veja [`desktop/README.md`](desktop/README.md) para detalhes de arquitetura, atalhos e build manual.

---

## Configuração

A instalação recomendada cria e utiliza `~/.zeus/.env` (ou outro diretório definido em `ZEUS_HOME`). Instalações antigas também podem ler um `.env` na raiz do projeto. Você pode editar as configurações pela interface do **Zeus Desktop** ou via CLI:

```bash
/config
/config set ZEUS_PROVIDER openrouter
/config set ZEUS_MODEL openrouter/auto
/config list-models google
```

Exemplo de `~/.zeus/.env`:

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
# GROQ_API_KEY=...
# XAI_API_KEY=...
# TOGETHER_API_KEY=...
# FIREWORKS_API_KEY=...
# COHERE_API_KEY=...

# Sandbox (se usar ferramentas de código isolado)
ZEUS_SANDBOX_URL=http://127.0.0.1:9876
```

## Model Context Protocol (MCP)

O Zeus pode se conectar a servidores MCP externos para expandir suas ferramentas (via CLI ou pelo painel de MCP do **Zeus Desktop**):

```bash
/mcp add gemini
/mcp add filesystem
/mcp add memory
/mcp list
/mcp reload
```

Ferramentas MCP são registradas automaticamente no agente com o prefixo `mcp_<servidor>_`.

---

## Recursos do Core

- **Ferramentas**: 50 ferramentas nativas em 8 categorias (sistema, arquivos, web, memória, aprendizado, git, scheduler e configuração). Veja [`docs/TOOLS.md`](docs/TOOLS.md).
- **Gateways**: Telegram, WhatsApp, Discord e Instagram Messaging (conta Profissional via API oficial da Meta). Veja [`docs/GATEWAY.md`](docs/GATEWAY.md).
- **Tarefas agendadas**:

```python
from zeus.tools.scheduler import schedule_task

schedule_task(
    command="ls -la /tmp",
    schedule="0 9 * * *",  # todo dia às 9h
    description="listar /tmp"
)
```

### Sandbox Go

A sandbox requer Linux x86_64, Go 1.20+, root e cgroup v2 com `cpu`, `memory` e `pids` habilitados, além de mount namespaces e `seccomp-bpf`. Ela falha fechada (*fail-closed*) se não puder aplicar esses controles e escuta apenas em loopback. Veja [`docs/SANDBOX.md`](docs/SANDBOX.md) para requisitos, limites e implantação.

Para instalação persistente, use o instalador `systemd` documentado em [`docs/INSTALACAO.md`](docs/INSTALACAO.md), que copia a sandbox para um diretório pertencente ao `root` (execute apenas a partir de uma revisão confiável e limpa do Git).

---

## Documentação

- [`docs/PROJETO.md`](docs/PROJETO.md) — visão geral e arquitetura de alto nível
- [`docs/INSTALACAO.md`](docs/INSTALACAO.md) — instalação local e systemd passo a passo
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — componentes internos
- [`docs/USAGE.md`](docs/USAGE.md) — guia completo de uso
- [`docs/TOOLS.md`](docs/TOOLS.md) — todas as 50 ferramentas
- [`docs/GATEWAY.md`](docs/GATEWAY.md) — gateways Telegram, WhatsApp, Discord e Instagram Messaging
- [`docs/SANDBOX.md`](docs/SANDBOX.md) — detalhes da sandbox Go
- [`docs/MCP.md`](docs/MCP.md) — Model Context Protocol
- [`docs/CONFIG.md`](docs/CONFIG.md) — gerenciamento de configurações
- [`docs/LEARNING.md`](docs/LEARNING.md) — aprendizado contínuo
- [`desktop/README.md`](desktop/README.md) — Zeus Desktop (Rust nativo), bridge JSONL e instalador

## Autor

- **Valdeir Pereira da Silva**
