# Ferramentas do Zeus

50 ferramentas registradas, auto-importadas em `zeus/__init__.py` e `zeus/cli/main.py`.

## Sistema (7)

| Ferramenta | Descrição |
|---|---|
| `run_terminal` | Executa comando shell no host (suporta `cwd`). |
| `run_sandboxed` | Executa comando shell dentro da sandbox Go isolada. |
| `run_background_command` | Executa comando shell assíncrono em background. |
| `command_status` | Consulta status/saída de um comando em background. |
| `terminate_command` | Encerra um comando em background pelo `command_id`. |
| `execute_python` | Executa código Python isolado na sandbox. |
| `execute_shell_script` | Executa script shell isolado na sandbox. |

## Arquivos (10)

| Ferramenta | Descrição |
|---|---|
| `read_file` | Lê linhas de arquivo de texto. |
| `write_file` | Cria ou sobrescreve arquivo. |
| `list_directory` | Lista arquivos e diretórios. |
| `search_files` | Busca conteúdo com regex. |
| `grep_search` | Busca regex de alta velocidade em arquivos do projeto. |
| `copy_file` | Copia arquivo ou diretório. |
| `move_file` | Move ou renomeia arquivo/diretório. |
| `delete_file` | Deleta arquivo. |
| `replace_file_content` | Substitui trecho em arquivo existente (gera diff). |
| `query_database` | Consulta SQL read-only no banco SQLite do Zeus. |

## Web (7)

| Ferramenta | Descrição |
|---|---|
| `web_search` | Busca na web (DuckDuckGo, Tavily, Serper). |
| `web_extract` | Extrai conteúdo legível de URL em Markdown. |
| `web_scrape_links` | Extrai todos os links de uma página. |
| `browser_navigate` | Navega com Chrome headless, retorna título + texto. |
| `browser_extract` | Extrai HTML/elementos via CSS selector. |
| `browser_click` | Clica elemento e retorna texto atualizado. |
| `browser_evaluate` | Avalia JavaScript na página. |

## Memória (10)

| Ferramenta | Descrição |
|---|---|
| `remember` | Armazena nota persistente. |
| `recall` | Recupera notas por chave. |
| `search_memory` | Busca notas na memória por palavra-chave. |
| `list_memories` | Lista chaves e contagem de notas. |
| `forget_memory` | Apaga todas as notas de uma chave. |
| `remember_user` | Armazena fato sobre o usuário. |
| `recall_user` | Recupera perfil do usuário. |
| `reflect_on_resolution` | Salva padrão problema/solução aprendido. |
| `search_past_learnings` | Busca aprendizados passados relevantes. |
| `list_recent_learnings` | Lista aprendizados mais recentes. |

## Aprendizado (1)

| Ferramenta | Descrição |
|---|---|
| `rate_learning` | Avalia se um aprendizado foi útil. |

## Git (8)

| Ferramenta | Descrição |
|---|---|
| `git_status` | Status do working tree. |
| `git_log` | Histórico de commits. |
| `git_diff` | Alterações. |
| `git_branch` | Lista branches. |
| `git_checkout` | Muda de branch. |
| `git_pull` | Pull do remote. |
| `git_push` | Push para remote. |
| `git_commit` | Commit com mensagem. |
| `git_clone` | Clona repositório remoto. |

## Scheduler (2)

| Ferramenta | Descrição |
|---|---|
| `schedule_task` | Agenda tarefa com cron expression. |
| `list_scheduled` | Lista tarefas agendadas. |
| `cancel_task` | Cancela tarefa pelo ID. |

## Configuração (3)

| Ferramenta | Descrição |
|---|---|
| `get_zeus_config` | Retorna configuração atual do Zeus. |
| `update_zeus_config` | Atualiza variável/chave de API no `.env`. |
| `list_available_models` | Lista provedores e modelos disponíveis. |
