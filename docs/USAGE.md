# Uso do Zeus

## Configuração

Configure via `.env` na raiz do projeto:

```bash
# Provedor e modelo
ZEUS_PROVIDER=opencode_go
ZEUS_MODEL=kimi-k2.7-code

# API keys (variam por provedor)
OPENCODE_GO_API_KEY=sk-...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
GOOGLE_API_KEY=...
DEEPSEEK_API_KEY=sk-...
MISTRAL_API_KEY=...

# Sandbox (opcional, para execute_python e run_sandboxed)
ZEUS_SANDBOX_URL=http://127.0.0.1:9876

# Gateway (quando usar)
ZEUS_TELEGRAM_TOKEN=...
ZEUS_TELEGRAM_ALLOWED_CHAT_IDS=123456
ZEUS_WHATSAPP_ALLOWED_NUMBERS=...
ZEUS_DISCORD_TOKEN=...
ZEUS_DISCORD_ALLOWED_USER_IDS=123456

# Memória SQLite (opcional, padrão true)
ZEUS_USE_SQLITE=true
```

## Executar

### CLI interativo

```bash
cd /home/vps28/Documentos/Dev/Zeus
source .venv/bin/activate
python -m zeus.cli
```

### Query única

```bash
python -m zeus.cli -q "liste arquivos do diretório atual"
python -m zeus.cli -q "execute python: print(2+2)" --provider openai --model gpt-4o
```

### Equipe multi-agente

```bash
python -m zeus.cli --team "tarefa complexa"
# ou dentro do modo interativo:
/team <tarefa>
```

## Comandos da CLI

Use `/models` para abrir o seletor de provedor e modelo. `/provider` continua funcionando como alias de compatibilidade.

| Comando | Descrição |
|---|---|
| `/sair`, `/quit`, `/exit` | Encerra |
| `/team <tarefa>` | Executa tarefa com equipe multi-agente |
| Ctrl+C | Interrompe resposta em andamento |

## Gateways

### Telegram

```bash
python -m zeus.gateway --platform telegram
```

### WhatsApp

```bash
# Primeiro: escanear QR code
cd gateway/whatsapp/baileys && node dist/index.js
# Depois: iniciar gateway
python -m zeus.gateway --platform whatsapp
```

### Discord

```bash
python -m zeus.gateway --platform discord
```

## Tarefas agendadas

O agente entende linguagem natural para agendar:

```
"agende uma tarefa que roda todo dia às 9h e lista arquivos do /tmp"
"schedule something to run every monday at 9am"
"liste as tarefas agendadas"
"cancele a tarefa com id abc123"
```

Ou via código:

```python
from zeus.tools.scheduler import schedule_task, list_scheduled, cancel_task

# Agendar
schedule_task(
    command="ls -la /tmp",
    schedule="0 9 * * *",
    description="listar /tmp todo dia às 9h"
)

# Listar
print(list_scheduled())

# Cancelar
cancel_task(task_id="abc123")
```

## Sandbox

Para usar `execute_python` e `run_sandboxed`, inicie a sandbox:

```bash
sudo ./sandbox/sandbox -addr 127.0.0.1:9876
```

## Testes

```bash
python -m pytest tests/ -q
```
