# Aprendizado Contínuo no Zeus

O Zeus pode aprender com cada resolução de problema, reutilizando padrões em tarefas futuras.

## Como funciona

1. **Captura manual** — via tool `reflect_on_resolution` ou comando `/learn add`.
2. **Captura automática** — ao final de uma sessão, se houver erros de ferramenta seguidos de sucesso, o agente extrai um padrão e salva.
3. **Recuperação** — antes de cada execução, o agente busca aprendizados relevantes e injeta no system prompt.
4. **Feedback** — o usuário pode avaliar aprendizados com `rate_learning` ou `/learn rate <id> +1/-1`.

## CLI `/learn`

```
/learn                          # menu
/learn list                     # lista aprendizados recentes
/learn search <query>           # busca relevantes
/learn add <problema> | <solução> [tags:a,b]
/learn rate <id> <+1/-1>        # feedback de utilidade
```

## Ferramentas

- `reflect_on_resolution` — salva problema/solução.
- `search_past_learnings` — busca aprendizados.
- `rate_learning` — avalia utilidade.
- `list_recent_learnings` — lista recentes.

## Banco de dados

Tabela `learnings` em `~/.zeus/zeus.db`:

| Coluna | Descrição |
|---|---|
| `problem` | Problema ou tarefa resumida |
| `solution` | Solução aplicada |
| `tools_used` | Ferramentas envolvidas (JSON array) |
| `tags` | Tags para agrupar (JSON array) |
| `effectiveness_score` | Score de relevância (sobe/desenso com feedback) |
| `failure_pattern` | Erro ou padrão de falha observado |

## Integração no agent loop

Em `zeus/core/agent.py`, antes de cada chamada LLM:

```python
learning_store = LearningStore(user_id=user_id)
learning_context = learning_store.format_context(user_input)
```

Se houver aprendizados relevantes, eles são adicionados ao system prompt.

Após sucesso, `extract_from_session()` analisa o histórico e salva automaticamente.

## Boas práticas

- Adicione tags específicas (ex: `docker`, `auth`, `pytest`) para facilitar buscas.
- Avalie aprendizados incorretos com `-1` para reduzir peso futuro.
- Aprendizados manuais (`/learn add`) têm score inicial maior que automáticos.
