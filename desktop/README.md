# Zeus Desktop (Rust Native)

Interface gráfica nativa de alto desempenho para o **Zeus Agent**, desenvolvida 100% em **Rust** utilizando **egui / eframe**.

## Características

- ⚡ **Ultra Rápido e Leve**: Inicialização instantânea, sem Electron, sem WebView e sem runtime Node/Python para a interface.
- 🎨 **Interface Moderna e Responsiva**: Tema escuro, renderização direta via GPU (wgpu/OpenGL/Wayland/X11).
- 💾 **Persistência Automática de Estado**: Projetos adicionados, conversas, modelo ativo, modo de segurança e preferências salvas em `~/.zeus/desktop_state.json`.
- 💻 **Blocos de Código com Destaque e Cópia**: Detecção automática de snippets de código Markdown com background escuro monoespaçado e botão "📋 Copiar Código" dedicado por snippet.
- ⌨️ **Input Multilinha e Histórico**: Suporte a mensagens e código multilinha (`Enter` para envio, `Shift + Enter` para quebra de linha) e navegação no histórico de prompts com as setas para cima/baixo (`↑`/`↓`).
- 📁 **Gerenciamento Completo de Projetos e Conversas**: Alternância de projetos, remoção de projetos da lista, exclusão individual de conversas (`🗑`) e exportação para Markdown (`📥`).
- 🔄 **Execução em Segundo Plano com Streaming**: Comunicação assíncrona com o processo do Zeus CLI em tempo real via canais `mpsc`.
- ⏹ **Controle e Cancelamento Limpo**: Botão de cancelamento que encerra a árvore inteira de subprocessos (`process_group(0)` + `SIGTERM` Unix) sem deixar zumbis.
- ⚙️ **Configuração Dinâmica**: Modais para Provedor, Modelo, Modo de Execução, Esforço de Raciocínio, Interpretador Python customizado, Catálogo de Ferramentas ReAct e presets de Servidores MCP.

## Pré-requisitos

- Rust e Cargo (instalados via `rustup`):
  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  ```

## Como Executar

### Modo Desenvolvimento

```bash
cd desktop
cargo run
```

### Compilar para Produção (Release)

Gera um binário único, compacto e otimizado (~15MB) em `target/release/zeus-desktop`:

```bash
cd desktop
cargo build --release
```

Para executar o binário compilado diretamente:

```bash
./target/release/zeus-desktop
```

## Estrutura Modular do Código

```
desktop/
├── Cargo.toml          # Dependências (eframe, egui, chrono, serde, serde_json, libc)
├── src/
│   ├── main.rs         # Inicialização do eframe e ciclo de vida
│   ├── app.rs          # Estrutura central ZeusApp e loop de eventos
│   ├── state.rs        # Modelos: Conversation, ChatMessage, ZeusMode, WorkerEvent
│   ├── config.rs       # Persistência de configuração (~/.zeus/desktop_state.json)
│   ├── process.rs      # Subprocessos, streaming, sanitização ANSI e cancelamento
│   ├── data/           # Catálogos estáticos
│   │   ├── commands.rs # Comandos do Zeus (/help, /mode, /plan, etc.)
│   │   ├── tools.rs    # Ferramentas nativas ReAct
│   │   └── providers.rs# Provedores e modelos LLM
│   └── ui/             # Componentes visuais
│       ├── header.rs   # Top bar com menu hamburger e status bar inferior
│       ├── sidebar.rs  # Painel lateral de Projetos e Conversas
│       ├── chat.rs     # Chat com blocos de código e input inteligente
│       └── modals/     # Configurações, Comandos, Ferramentas, MCP, Sobre, Add Project
└── README.md           # Documentação
```

## Autor

Valdeir Pereira da Silva
