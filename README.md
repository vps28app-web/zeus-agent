# Zeus

Agent harness minimalista escrito em Python.

**Conceito**: agente = modelo + harness. Zeus é o harness: o loop de pensar→agir→observar, registro de ferramentas, roteamento de modelos, memória persistente e execução local.

## Estrutura

```
zeus/
├── core/        # agent loop, tool registry, model router
├── tools/       # ferramentas disponíveis para o agente
├── memory/      # persistência de memória e histórico
├── cli/         # interface de linha de comando
├── providers/   # adaptadores para provedores de LLM
└── config/      # configuração e ambiente
```

## Instalação rápida

```bash
cd /home/vps28/Documentos/Dev/Zeus
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python -m zeus.cli
```

## Documentação

Veja a pasta `docs/`.
