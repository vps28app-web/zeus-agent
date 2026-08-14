# Arquitetura do Zeus

## Visão geral

Zeus é um **agent harness** minimalista: o código que transforma um LLM em um agente autônomo.

```
Usuário -> CLI -> Agent Loop -> Model Router -> LLM
                          |
                          v
                    Tool Registry -> Ferramentas
                          |
                          v
                       Memória
```

## Componentes

### 1. Agent Loop (`zeus/core/agent.py`)

Implementa o padrão **ReAct**:
1. Recebe a mensagem do usuário.
2. Envia para o LLM com as ferramentas disponíveis.
3. Se o LLM responder com chamadas de ferramenta, executa-as.
4. Retorna os resultados ao LLM.
5. Repete até obter uma resposta final ou atingir `max_turns`.

### 2. Tool Registry (`zeus/core/registry.py`)

Registra e resolve ferramentas. Cada ferramenta tem:
- nome
- descrição (usada pelo LLM)
- schema de parâmetros
- handler (função Python)
- variáveis de ambiente necessárias

### 3. Model Router (`zeus/core/router.py`)

Provê interface unificada para provedores de LLM. Atualmente suporta:
- OpenRouter
- Ollama (local)

Pode ser estendido para Anthropic, OpenAI, Google, etc.

### 4. Ferramentas (`zeus/tools/`)

- `terminal`: executa comandos shell.
- `file`: lê, escreve, lista e busca arquivos.
- `web`: busca na web e extrai conteúdo de URLs.
- `memory_tools`: permite ao agente guardar e recuperar notas.

### 5. Memória (`zeus/memory/store.py`)

Armazenamento JSON simples em `~/.zeus/memory.json`. O agente pode guardar notas entre sessões.

### 6. CLI (`zeus/cli/`)

Interface interativa via `prompt_toolkit`. Suporta:
- modo interativo
- query única com `-q`
- histórico local

## Próximos passos sugeridos

1. Adicionar testes unitários.
2. Implementar compressão de contexto.
3. Adicionar delegação de sub-agentes.
4. Criar runtime Go/Rust para sandbox isolada.
5. Adicionar gateway para Telegram/Discord.
