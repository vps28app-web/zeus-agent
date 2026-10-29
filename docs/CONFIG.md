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
/config set OPENCODE_GO_API_KEY # abre entrada mascarada para criar/substituir a chave
/config list-models google      # lista modelos de um provider
```

Para chaves e outros segredos, omita o valor: o Zeus solicita a entrada mascarada e grava em `~/.zeus/.env`. Não informe o segredo na mesma linha do comando, pois isso pode salvá-lo no histórico do terminal.

O comando `zeus setup` abre o assistente interativo de provedor/modelo e só solicita credenciais obrigatórias que ainda não estejam configuradas. Para trocar uma chave existente, use `/config set NOME_DA_CHAVE` na CLI interativa; isso abre a entrada mascarada.

Alterações em `ZEUS_PROVIDER` ou `ZEUS_MODEL` são aplicadas em tempo real na sessão ativa.

## Autenticação Google Gemini via browser (OAuth)

Em vez da chave cara do Google AI Studio, você pode autenticar pelo navegador usando OAuth 2.0:

1. Vá em https://console.cloud.google.com/apis/credentials
2. Crie credenciais **OAuth 2.0 Client ID** do tipo **Desktop app**
3. Configure a **Tela de permissão OAuth** (nome, e-mail de suporte, e-mail do desenvolvedor)
4. Ative a **Gemini API** no projeto
5. Adicione no `~/.zeus/.env`:

```bash
GOOGLE_OAUTH_CLIENT_ID=SEU_CLIENT_ID.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=SEU_CLIENT_SECRET
```

6. Defina o provider OAuth:

```bash
/config set ZEUS_PROVIDER google_auth
/config set ZEUS_MODEL gemini-3.6-flash
```

7. No CLI do Zeus, execute:

```
/auth google
```

Isso abre o navegador, redireciona de volta para `http://127.0.0.1:<porta>` e salva o token em `~/.zeus/google_oauth_credentials.json`.

Comandos úteis:

```
/auth status   # verifica se o token está ativo
/auth revoke   # remove as credenciais salvas
```

Para usar chave de API em vez de OAuth, defina `ZEUS_PROVIDER=google_api` e configure `GEMINI_API_KEY`.

## Variáveis suportadas

| Variável | Descrição |
|---|---|
| `ZEUS_PROVIDER` | `opencode_go`, `openrouter`, `openai`, `anthropic`, `google`, `deepseek`, `mistral`, `ollama`, `groq`, `xai`, `together`, `fireworks` ou `cohere` |
| `ZEUS_MODEL` | Modelo específico do provedor |
| `OPENCODE_GO_API_KEY` | Chave do OpenCode Go |
| `OPENROUTER_API_KEY` | Chave do OpenRouter |
| `OPENAI_API_KEY` | Chave da OpenAI |
| `ANTHROPIC_API_KEY` | Chave da Anthropic |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Chave do Google AI Studio (aliases sincronizados). Usada pelo provider `google_api`. |
| `GOOGLE_OAUTH_CLIENT_ID` | Client ID OAuth para autenticação browser do Gemini (provider `google_auth`) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Client secret OAuth para autenticação browser do Gemini (provider `google_auth`) |
| `DEEPSEEK_API_KEY` | Chave do DeepSeek |
| `MISTRAL_API_KEY` | Chave do Mistral |
| `GROQ_API_KEY` | Chave da Groq |
| `XAI_API_KEY` | Chave da xAI |
| `TOGETHER_API_KEY` | Chave da Together AI |
| `FIREWORKS_API_KEY` | Chave da Fireworks AI |
| `COHERE_API_KEY` | Chave da Cohere |
| `ZEUS_SANDBOX_URL` | URL do sandbox Go (padrão: `http://127.0.0.1:9876`) |

## Programático

```python
from zeus.tools.config_tools import get_zeus_config, update_zeus_config

config = get_zeus_config()
update_zeus_config("ZEUS_MODEL", "openrouter/auto")
```
