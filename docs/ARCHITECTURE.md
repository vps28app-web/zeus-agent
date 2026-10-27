# Arquitetura do Zeus

> Para a visão geral, instalação, configuração e limites operacionais atualizados, consulte [`PROJETO.md`](PROJETO.md). Esta página detalha os componentes internos.

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
| `google` / `google_api` | generativelanguage.googleapis.com | Gemini API |
| `google_auth` | OAuth browser flow | Gemini API via OAuth |
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

- `store.py` — `remember`/`recall`; SQLite é o padrão (`ZEUS_USE_SQLITE=true`) e JSON em `~/.zeus/memory.json` é alternativa.
- `session_log.py` — histórico JSONL em `~/.zeus/logs/` e persistência SQLite opcional.

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
- `whatsapp.py` — gateway Python ligado à ponte Baileys (Node.js)
- `discord.py` — integração via `discord.py`
- Instagram Messaging — webhook HTTPS pela API oficial da Meta para conta profissional

### 12. Sandbox Go (`sandbox/`)

Serviço HTTP Go em loopback (`127.0.0.1:9876`); `/run` exige token bearer configurado. Para cada execução:

- cria workspace temporário privado e chroot em tmpfs;
- usa namespaces mount, PID, network, UTS e IPC;
- monta `/bin`, `/usr` e bibliotecas read-only, `nosuid` e `nodev`, sem montar o `/etc` do host;
- aplica cgroups v2 para memória, quota de CPU e PIDs;
- instala seccomp-bpf obrigatoriamente e reduz o payload ao usuário `nobody`;
- limita tempo, saída, corpo HTTP e execuções concorrentes; rejeita requisições fora dos limites.

Se root, namespaces, seccomp ou limites cgroup não puderem ser aplicados, falha fechada. Requer Linux amd64 e cgroup v2; não é uma barreira absoluta contra vulnerabilidades do kernel. Detalhes e implantação: [`SANDBOX.md`](SANDBOX.md).
