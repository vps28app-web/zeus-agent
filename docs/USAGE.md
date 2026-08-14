# Uso do Zeus

## Configuração

Crie o arquivo `~/.zeus/config.yaml`:

```yaml
provider: opencode_go
model: kimi-k2.7-code
max_turns: 20
```

Ou use variáveis de ambiente:

```bash
export ZEUS_PROVIDER=opencode_go
export ZEUS_MODEL=kimi-k2.7-code
export OPENCODE_GO_API_KEY=sua-chave
```

## Executar

### Modo interativo

```bash
cd /home/vps28/Documentos/Dev/Zeus
source .venv/bin/activate
python -m zeus.cli
```

### Query única

```bash
python -m zeus.cli -q "Liste os arquivos do diretório atual"
```

## Comandos da CLI

- `/sair`, `/quit`, `/exit`: encerra.

## Ferramentas disponíveis

- `run_terminal`: executa comandos shell.
- `read_file`: lê arquivo de texto.
- `write_file`: escreve arquivo de texto.
- `list_directory`: lista diretório.
- `search_files`: busca por regex em arquivos.
- `web_search`: busca na web (requer SERPER_API_KEY).
- `web_extract`: extrai conteúdo de URL.
- `remember`: armazena nota na memória.
- `recall`: recupera notas da memória.
