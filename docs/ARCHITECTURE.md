# Arquitetura do Zeus

## Visão geral

```
Usuário -> CLI/Gateway -> Agent Loop (ReAct) -> Model Router -> LLM
                          |
                          v
                    Tool Registry -> Ferramentas
                          |
                          v
                    Memória + Observabilidade
                          |
                          v
                    Scheduler (polls tarefas prontas)
```

## Componentes

### 1. Agent Loop (`zeus/core/agent.py`)

Padrão **ReAct** (Reason + Act):
1. Recebe mensagem do usuário.
2. Envia para o LLM com ferramentas disponíveis.
3. Se LLM chamar ferramenta, executa e retorna resultado.
4. Repete até resposta final ou `max_turns`.

### 2. Tool Registry (`zeus/core/registry.py`)

Cada ferramenta tem: nome, descrição (usada pelo LLM), schema JSON-Schema, handler (função Python), variáveis de ambiente necessárias. Auto-registra via import.

### 3. Model Router (`zeus/core/router.py`)

Interface unificada para 8 provedores:

| Provider | API | Formato |
|---|---|---|
| `openrouter` | openrouter.ai | OpenAI-like |
| `ollama` | localhost:11434 | custom |
| `opencode_go` | api.opencode.co | OpenAI-like |
| `openai` | api.openai.com | OpenAI-like |
| `anthropic` | api.anthropic.com | Messages API |
| `google` | generativelanguage.googleapis.com | Gemini |
| `deepseek` | api.deepseek.com | OpenAI-like |
| `mistral` | api.mistral.ai | OpenAI-like |

### 4. Sistema de Arquivos (`zeus/tools/terminal.py`, `file.py`)

- `run_terminal` — executa no host
- `run_sandboxed` — executa na sandbox
- `read_file`, `write_file`, `list_directory`, `search_files`

### 5. Web (`zeus/tools/web.py`)

- `web_search` — busca (requer `SERPER_API_KEY`)
- `web_extract` — extrai conteúdo de URL

### 6. Memória (`zeus/memory/`)

- `store.py` — `remember`/`recall`, JSON por padrão, SQLite opcional
- `session_log.py` — logs de sessão em JSONL + SQLite

### 7. Banco de Dados (`zeus/db/`)

Schema SQLite:
- `memories` — notas persistentes
- `sessions` — sessões de chat
- `turns` — mensagens por sessão
- `metrics` — latência, tokens, erros por chamada
- `scheduled_tasks` — tarefas cron

### 8. Observabilidade (`zeus/observability/`)

- `metrics.py` — coletor de métricas por sessão
- `cost.py` — estimador de custo por provider/model
- `tracing.py` — spans estruturados
- `reporter.py` — relatório final de uso

### 9. Scheduler (`zeus/scheduler/runner.py`)

Thread polling a cada 60s. Verifica `scheduled_tasks` no SQLite por tarefas prontas e executa via agente. Auto-inicia quando qualquer gateway sobe.

### 10. Multi-Agent (`zeus/core/team.py`)

- `Team` — coordenador que planeja e delega
- `Worker` — agente especializado (coder, researcher, shell, reviewer, generalist)

### 11. Gateways (`zeus/gateway/`)

- `telegram.py` — polling HTTP no Bot API
- `whatsapp.py` — ponte Python + Baileys (Node.js)
- `discord.py` — discord.py com intents

### 12. Sandbox Go (`sandbox/`)

Binary Go isolado rodando em `127.0.0.1:9876`:
- chroot para `/tmp/zeus-rootfs`
- Linux namespaces (mount, PID, network, UTS, IPC)
- cgroups v2 (memória e CPU)
- seccomp-bpf whitelist (52 syscalls permitidos)
- Drop de privilégios para `nobody` (uid 65534)
- Whitelist de binários permitidos
