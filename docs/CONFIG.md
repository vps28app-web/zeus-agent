# Configuração do Zeus

O Zeus lê variáveis de ambiente de dois arquivos `.env`, em ordem de prioridade:

1. `~/.zeus/.env` (global, recomendado)
2. `.env` na pasta atual (projeto)

Use `python-dotenv` para carregar e `ZEUS_HOME` para trocar a pasta global.

## CLI `/config`

No modo interativo:

```
/config                         # mostra configuração atual
/config get ZEUS_PROVIDER       # lê valor de uma variável
/config set ZEUS_PROVIDER openrouter
/config set ZEUS_MODEL openrouter/auto
/config list-models google      # lista modelos de um provider
```

Alterações em `ZEUS_PROVIDER` ou `ZEUS_MODEL` são aplicadas em tempo real na sessão ativa.

## Variáveis suportadas

| Variável | Descrição |
|---|---|
| `ZEUS_PROVIDER` | Provedor LLM: `opencode_go`, `openrouter`, `openai`, `anthropic`, `google`, `deepseek`, `mistral`, `ollama` |
| `ZEUS_MODEL` | Modelo específico do provedor |
| `OPENCODE_GO_API_KEY` | Chave do OpenCode Go |
| `OPENROUTER_API_KEY` | Chave do OpenRouter |
| `OPENAI_API_KEY` | Chave da OpenAI |
| `ANTHROPIC_API_KEY` | Chave da Anthropic |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Chave do Google Gemini (aliases sincronizados) |
| `DEEPSEEK_API_KEY` | Chave do DeepSeek |
| `MISTRAL_API_KEY` | Chave do Mistral |
| `ZEUS_SANDBOX_URL` | URL do sandbox Go (padrão: `http://127.0.0.1:9876`) |

## Programático

```python
from zeus.tools.config_tools import get_zeus_config, update_zeus_config

config = get_zeus_config()
update_zeus_config("ZEUS_MODEL", "openrouter/auto")
```
