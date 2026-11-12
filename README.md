# Zeus

Agent harness minimalista escrito em Python. Agente = modelo + harness. Zeus é o harness: loop ReAct, registro de ferramentas, roteamento de modelos, memória persistente, sandbox isolada, observabilidade e execução em background.

O projeto conta com duas interfaces principais sobre o mesmo core:
- **Zeus CLI**: interface interativa no terminal, modo single-query, gateways e automações.
- **Zeus Desktop**: cliente gráfico nativo em Rust (`eframe`/`egui`) integrado ao core via JSONL.

## Estrutura

```
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
```

## Instalação

### Zeus CLI (Core)

Em Linux/macOS com Python 3.8+ e Git, clone o repositório e execute o instalador sem `sudo`:

```bash
git clone https://github.com/vps28app-web/zeus-agent.git
cd zeus-agent
./scripts/install.sh
zeus setup
```

O instalador cria `.venv`, instala o pacote e os comandos `zeus`/`zeus-gateway`, cria a configuração privada em `~/.zeus/.env` e gera o token da sandbox. Em Linux amd64, se Go estiver disponível, também compila a sandbox opcional. Detalhes e alternativas: [`docs/INSTALACAO.md`](docs/INSTALACAO.md).

### Zeus Desktop (Rust Nativo)

Para instalar o cliente gráfico nativo ([`desktop/README.md`](desktop/README.md)) sem `sudo` (requer `cargo`/Rust para compilar ou `--no-build` se o binário release já existir):

```bash
./scripts/install-desktop.sh
# ou via npm:
npm run install:desktop
```

O instalador verifica automaticamente a base Python do Zeus Core (`.venv`, comandos e `~/.zeus/.env`), executando `./scripts/install.sh` quando necessário, compila o binário release e registra o comando `~/.local/bin/zeus-desktop`, o atalho `.desktop` e o ícone SVG no menu de aplicativos.

Opções úteis:
- `./scripts/install-desktop.sh --no-build` — usa o binário em `desktop/target/release/zeus-desktop` sem recompilar
- `./scripts/install-desktop.sh --with-core` — força a reinstalação/atualização do Zeus Core antes do Desktop
- `./scripts/install-desktop.sh --skip-core` — instala apenas o binário Desktop sem validar o Zeus Core
- `./scripts/uninstall-desktop.sh` — remove o cliente Desktop (adicione `--state` para apagar também `~/.zeus/desktop-state.json`)

### Comando `zeus` global via npm

Depois de instalar (por qualquer fluxo), você pode expor `zeus` e `zeus-gateway` como comandos globais que funcionam em qualquer diretório:

```bash
npm install -g git+https://github.com/vps28app-web/zeus-agent.git
# ou, dentro de um checkout: npm install -g .
zeus --version   # em qualquer diretório
```

O launcher não instala o Zeus: ele localiza a instalação existente (`ZEUS_INSTALL_DIR`, checkout acima do diretório atual, registro `~/.zeus/install-dir` ou `~/.local/share/zeus-agent`) e a executa preservando o diretório atual como workspace. O `.env` da raiz do checkout continua carregando mesmo executando fora dele. Requer Node 18+; funciona em qualquer plataforma com Node, sem as restrições de Linux amd64 do fluxo completo abaixo.

Em Debian/Ubuntu amd64 com Go 1.20+ disponível nos repositórios apt, também há um fluxo npm que prepara as dependências e instala/inicia a sandbox systemd em uma execução. Direto do GitHub, sem clonar nada:

```bash
npx --yes --package=git+https://github.com/vps28app-web/zeus-agent.git zeus-install
```

Esse comando funciona em qualquer diretório. Se você já tem um checkout e está na raiz dele, o equivalente é:

```bash
npm run install:zeus
```

Atenção: `npm run` exige o `package.json` no diretório atual — fora do checkout ele falha com `ENOENT`; use o `npx` acima nesse caso.

Requer Node.js 18+, npm e Git. O instalador pede confirmação antes de instalar pacotes de sistema e solicitar autorização administrativa para o serviço da sandbox.

Para remover, use `zeus-uninstall` (publicado pelo pacote npm, funciona de qualquer diretório) ou `./scripts/uninstall.sh` num checkout — remove launchers e registro; flags opcionais para estado, clone npm e `.venv` — e `npm uninstall -g zeus-agent-installer` para tirar os comandos globais. Detalhes: [`docs/INSTALACAO.md`](docs/INSTALACAO.md).

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
# GROQ_API_KEY=...
# XAI_API_KEY=...
# TOGETHER_API_KEY=...
# FIREWORKS_API_KEY=...
# COHERE_API_KEY=...

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

## Zeus Desktop

O diretório `desktop/` contém o cliente gráfico nativo do Zeus escrito em Rust (`eframe`/`egui`), conectado ao harness Python via JSONL (`zeus --desktop-json` e `zeus --desktop-catalog`):

- Chat em streaming com renderização Markdown e blocos recolhíveis de *reasoning* e chamadas de ferramenta (*tool calls*)
- Aprovações interativas *Human-in-the-Loop* para execução de ferramentas sensíveis
- Seleção dinâmica de provedor, modelo, esforço de raciocínio (`ZEUS_REASONING_EFFORT`) e gerenciamento de chaves em `~/.zeus/.env` e servidores MCP
- Painel lateral com histórico de sessões, métricas de observabilidade, tarefas agendadas e memória persistente

Após instalar, execute `zeus-desktop` no terminal ou abra **Zeus Desktop** pelo menu de aplicativos. Veja [`desktop/README.md`](desktop/README.md) para detalhes de arquitetura e build manual.

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
- [`desktop/README.md`](desktop/README.md) — Zeus Desktop (Rust nativo), bridge JSONL e instalador

## Autor

- **Valdeir Pereira da Silva**

