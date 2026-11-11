# Checklist de Evolução — Zeus Desktop (Rust Native)

Plano completo para resolver as lacunas de integração com o core Python (`zeus`), bugs de UX/renderização e funcionalidades pendentes no `zeus-desktop`.

---

## Fase 1 — Ponte Estruturada Python ↔ Rust & Core (`zeus/`)

- [x] **Criar módulo `zeus/cli/desktop_bridge.py` e flag `--desktop-json` em `zeus/cli/main.py`**
  - [x] Protocolo JSON Lines (JSONL) bidirecional via `stdout`/`stdin` (`stream_chunk`, `tool_start`, `tool_result`, `permission_request`, `metrics`, `status`, `error`, `done`).
  - [x] Subcomando/flag `--desktop-catalog` retornando provedores, modelos, comandos `/`, ferramentas (`REGISTRY`) e configuração MCP em JSON.
  - [x] Suporte completo a slash commands no modo desktop (`/help`, `/mode`, `/plan`, `/team`, `/mcp`, `/config`, `/learn`, `/brain`, `/summary`, `/skills`, `/reset`, `/new`, `/auth`).
  - [x] Inicializar servidores MCP (`MCPManager.get_instance().start_all()`) antes da execução no modo desktop.
  - [x] Habilitar streaming real de tokens (`stream=True`, `stream_callback`) e envio de métricas reais (tokens de entrada/saída, latência e custo estimado).
  - [x] Suportar solicitações interativas (Human-in-the-Loop) via `stdin` (`permission_response`): confirmação de terminal (`ZeusMode::Terminal`), permissão de arquivo, confirmação de `/plan`, senha `sudo`, usuário/senha SSH.
- [x] **Suportar `ZEUS_REASONING_EFFORT` no roteamento de modelos (`zeus/core/router.py` / providers)**
  - [x] Normalizar valores (`minimal`/`low`/`medium`/`high`, aceitando também termos em PT-BR como `mínimo`/`médio`/`alto`) e encaminhar `reasoning_effort` nos providers compatíveis quando aplicável.

---

## Fase 2 — Worker, Estado e Persistência no Rust (`desktop/src/`)

- [x] **Atualizar `desktop/src/process.rs`**
  - [x] Invocar `python -m zeus.cli --desktop-json` com `stdin`/`stdout`/`stderr` em pipe e parsear eventos JSONL em tempo real.
  - [x] Manter fallback para saída de texto caso receba linhas não-JSON, corrigindo `sanitize_terminal_output` para **preservar indentação à esquerda** (não usar `.trim()` destrutivo no início das linhas).
  - [x] Implementar envio de respostas de permissão via `stdin` para a bridge Python.
  - [x] Carregar catálogo dinâmico (`--desktop-catalog`) de forma assíncrona ao iniciar ou trocar de projeto.
- [x] **Atualizar `desktop/src/state.rs`, `desktop/src/config.rs` e `desktop/src/app.rs`**
  - [x] Adicionar `session_id` único persistente por conversa (ex.: `desktop_<timestamp>_<id>`) para evitar colisões no `zeus.db` ao recriar `desktop_state.json`.
  - [x] Vincular conversas ao projeto (`project_path`) e permitir filtrar conversas na sidebar (do projeto ativo ou todas).
  - [x] Estruturar eventos de ferramentas e métricas reais por conversa (`ToolExecution`, `actual_input_tokens`, `actual_output_tokens`, `total_cost_usd`, `llm_calls`, `total_latency_ms`).
  - [x] Corrigir `auto_scroll` em `WorkerEvent::Finished` para respeitar a configuração do usuário (`self.auto_scroll`).
  - [x] Evitar gravação redundante em disco a cada evento de streaming (salvar por marcação `dirty` com debounce e ao finalizar/fechar via `on_exit`).

---

## Fase 3 — Interface, UX e Funcionalidades Pendentes (`desktop/src/ui/`)

- [x] **Renderização rica e editor no Chat (`desktop/src/ui/chat.rs`)**
  - [x] Suportar blocos de código ainda abertos durante streaming (` ```lang ` sem fechamento final).
  - [x] Renderizar Markdown básico: títulos (`#`, `##`, `###`), listas (`-`, `*`), citações (`>`), **negrito**, *itálico*, código inline (`` `...` ``) e links clicáveis.
  - [x] Exibir chamadas de ferramentas (`tool_start` / `tool_result`) em cards colapsáveis separados da resposta final.
  - [x] Adicionar ações por mensagem: editar/reenviar último prompt, anexar arquivos do projeto (`📎`) e feedback visual de cópia.
  - [x] Padronizar seletor de raciocínio (`Mínimo`, `Baixo`, `Médio`, `Alto`) mapeando para `minimal`/`low`/`medium`/`high`.
- [x] **Modal Interativo de Permissão / Human-in-the-Loop (`desktop/src/ui/modals/permission.rs`)**
  - [x] Exibir solicitação de confirmação (comando terminal, escrita de arquivo, `/plan`, senha `sudo` mascarada, credencial SSH) com botões Permitir uma vez / Sempre / Persistir / Negar.
- [x] **Configuração real de `.env` (API Keys), MCP e Ecossistema (`settings.rs`, `mcp.rs`, `sidebar.rs`, `header.rs`, `ecosystem.rs`)**
  - [x] Adicionar gestão de chaves de API (`~/.zeus/.env`) com máscara de segurança e botão de autenticação `/auth google` em `settings.rs`.
  - [x] Transformar `mcp.rs` em gerenciador real de `~/.zeus/mcp_servers.json` (listar, adicionar via formulário ou preset, habilitar/desabilitar, remover e testar).
  - [x] Adicionar filtro por projeto, busca e renomeação inline de conversas na `sidebar.rs`.
  - [x] Exibir métricas reais (tokens entrada/saída, latência e custo) no `header.rs`, além do modal **Painel do Ecossistema Zeus** (`ecosystem.rs`: métricas, tarefas agendadas e memória persistente).
  - [x] Melhorar seletor de pasta (`zenity` / `kdialog` / `yad` / fallback modal) e exportação de conversa (salvar em `~/.zeus/exports/` ou pasta configurada, com feedback na barra inferior).

---

## Fase 4 — Testes, Build e Validação Final

- [x] **Testes Python (`tests/test_desktop_bridge.py`)**
  - [x] Cobrir `--desktop-catalog`, comandos `/` via bridge, streaming de chunks/tools, permissões via `stdin`, métricas e `normalize_reasoning_effort`.
- [x] **Testes Rust (`desktop/src/`)**
  - [x] Cobrir `sanitize_terminal_output` (preservando indentação), parsing de eventos JSONL, Markdown / blocos abertos, `DesktopConfig::load_from_path/save_to_path`, histórico de prompts, eventos de streaming/tools e preservação de `auto_scroll`.
- [x] **Validação completa**
  - [x] Executar `pytest` (`test_desktop_bridge.py`, `test_cli.py`, `test_router.py`: 58 passed) e `cargo test` (10 passed) + `cargo build --release` em `desktop/` (concluído sem warnings).
  - [x] Atualizar este `CHECKLIST.md` com todos os itens concluídos.
