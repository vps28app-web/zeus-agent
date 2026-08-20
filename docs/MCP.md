# Model Context Protocol (MCP) no Zeus

O Zeus implementa cliente e servidor MCP, permitindo expandir ferramentas com servidores externos e exportar as ferramentas do Zeus para clients como Claude Desktop e Cursor.

## Cliente MCP

Conecta o Zeus a servidores MCP externos via `stdio` ou `SSE`.

### CLI `/mcp`

No modo interativo:

```
/mcp list                       # lista servidores e status
/mcp add gemini                 # preset: ativa grounding e code execution
/mcp add filesystem             # preset: acesso ao filesystem atual
/mcp add memory                 # preset: memória MCP
/mcp add github                 # preset: GitHub MCP
/mcp add meu npx -y @modelcontextprotocol/server-sqlite /caminho/db.sqlite
/mcp remove <nome>
/mcp reload
```

Ferramentas dos servidores ativos são registradas no agente com nome `mcp_<servidor>_<ferramenta>`.

### Configuração persistente

Servidores adicionados via `/mcp add` são salvos em `~/.zeus/mcp_servers.json`.

### Presets suportados

| Nome | Comando | Requisito |
|---|---|---|
| `gemini` | `npx -y @houtini/gemini-mcp` | `GEMINI_API_KEY` |
| `filesystem` | `npx -y @modelcontextprotocol/server-filesystem <cwd>` | Node.js |
| `memory` | `npx -y @modelcontextprotocol/server-memory` | Node.js |
| `github` | `npx -y @modelcontextprotocol/server-github` | `GITHUB_PERSONAL_ACCESS_TOKEN` |

## Servidor MCP

Expor as ferramentas do Zeus via stdio JSON-RPC:

```bash
python -m zeus.mcp.server
```

Métodos suportados:

- `initialize`
- `notifications/initialized`
- `tools/list`
- `tools/call`

## Programático

```python
from zeus.mcp import get_mcp_manager

mgr = get_mcp_manager()
mgr.start_all()
mgr.add_server("filesystem", "npx", args=["-y", "@modelcontextprotocol/server-filesystem", "."])
```
