# Ferramentas do Zeus

29 ferramentas registradas, auto-importadas em `zeus/__init__.py`.

## Sistema (3)

### run_terminal
Executa comando shell no host (sem isolamento).
```json
{"command": "ls -la", "timeout": 60}
```

### run_sandboxed
Executa comando shell dentro da sandbox Go isolada.
```json
{"command": "python3 -c 'print(2+2)'", "timeout": 30}
```

### query_database
Consulta SQL read-only no banco SQLite do Zeus.
```json
{"query": "SELECT * FROM memories WHERE key = 'general'", "limit": 100}
```

## Arquivos (4)

### read_file
Lê linhas de arquivo de texto.
```json
{"path": "/tmp/arquivo.txt", "offset": 1, "limit": 2000}
```

### write_file
Cria ou sobrescreve arquivo (cria diretórios pais automaticamente).
```json
{"path": "/tmp/novo.txt", "content": "conteúdo..."}
```

### list_directory
Lista arquivos e diretórios.
```json
{"path": "/tmp"}
```

### search_files
Busca conteúdo com regex.
```json
{"pattern": "def funcao", "path": "."}
```

## Web (2)

### web_search
Busca na web via Serper.
```json
{"query": "termo para buscar", "limit": 5}
```
Requer: `SERPER_API_KEY`

### web_extract
Extrai conteúdo de URL.
```json
{"url": "https://example.com", "char_limit": 15000}
```

## Memória (2)

### remember
Armazena nota persistente.
```json
{"note": "valor importante", "key": "general"}
```

### recall
Recupera notas por chave.
```json
{"key": "general"}
```

## Git (8)

### git_status
Mostra estado do working tree.
```json
{"repo_path": "."}
```

### git_log
Mostra histórico de commits.
```json
{"repo_path": ".", "max_count": 10, "oneline": true}
```

### git_diff
Mostra alterações.
```json
{"repo_path": ".", "staged": false, "target": "HEAD~1"}
```

### git_branch
Lista branches.
```json
{"repo_path": ".", "all_branches": false}
```

### git_checkout
Muda de branch.
```json
{"repo_path": ".", "branch": "main"}
```

### git_pull
Pull do remote.
```json
{"repo_path": ".", "remote": "origin", "branch": "main"}
```

### git_push
Push para remote.
```json
{"repo_path": ".", "remote": "origin", "branch": "main"}
```

### git_commit
Commit com mensagem.
```json
{"repo_path": ".", "message": "fix: corrigir bug", "add_all": false}
```

### git_clone
Clona repositório.
```json
{"repo_url": "https://github.com/user/repo.git", "target_path": "/tmp/repo", "depth": 1}
```

## Execução de código (2)

### execute_python
Executa Python na sandbox isolada.
```json
{"code": "print([x**2 for x in range(5)])", "timeout": 30}
```

### execute_shell_script
Executa script shell na sandbox.
```json
{"script": "echo hello && ls /tmp", "timeout": 30}
```

## Browser/CDP (4)

### browser_navigate
Navega para URL com Chrome headless, retorna título e texto visível.
```json
{"url": "https://example.com", "wait_seconds": 2.0}
```

### browser_extract
Extrai HTML ou elementos via CSS selector.
```json
{"url": "https://example.com", "selector": "h1", "wait_seconds": 2.0}
```

### browser_click
Clica elemento via CSS selector.
```json
{"url": "https://example.com", "selector": "#botao", "wait_seconds": 2.0}
```

### browser_evaluate
Avalia JavaScript na página.
```json
{"url": "https://example.com", "expression": "document.title", "wait_seconds": 2.0}
```

## Scheduler (3)

### schedule_task
Agenda tarefa com cron expression.
```json
{"command": "ls -la /tmp", "schedule": "0 9 * * *", "description": "listar /tmp"}
```

### list_scheduled
Lista todas as tarefas agendadas.
```json
{}
```

### cancel_task
Cancela tarefa pelo ID.
```json
{"task_id": "abc123"}
```
