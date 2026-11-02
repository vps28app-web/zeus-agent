# Zeus Desktop (Rust Native)

Interface gráfica nativa de alto desempenho para o **Zeus Agent**, desenvolvida 100% em **Rust** utilizando **egui / eframe**.

## Características

- ⚡ **Ultra Rápido e Leve**: Inicialização instantânea, sem Electron, sem WebView e sem runtime Node/Python para a interface.
- 🎨 **Interface Moderna e Responsiva**: Tema escuro, renderização direta via GPU (wgpu/OpenGL/Wayland/X11).
- 🔄 **Execução em Segundo Plano com Streaming**: Comunicação assíncrona com o processo do Zeus CLI em tempo real.
- ⏹ **Controle de Execução**: Botão de cancelamento imediato (SIGTERM) para parar comandos em andamento.
- 📁 **Seletor de Projetos**: Alterne rapidamente entre projetos conhecidos (`Zeus`, `GuiaGps`, `REA`) ou defina qualquer diretório de trabalho.
- 📋 **Recursos de Produtividade**: Cópia rápida de mensagens, histórico com timestamps e controle de limpeza de sessão.

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

Gera um binário único, compacto e otimizado em `target/release/zeus-desktop`:

```bash
cd desktop
cargo build --release
```

Para executar o binário compilado diretamente:

```bash
./target/release/zeus-desktop
```

## Estrutura do Código

```
desktop/
├── Cargo.toml          # Configurações do pacote e dependências Rust
├── src/
│   └── main.rs         # Aplicação desktop completa (UI, Worker Thread e subprocessos)
└── README.md           # Documentação
```

## Autor

Valdeir Pereira da Silva
