# Zeus Desktop (Tauri)

Interface gráfica para o Zeus Agent, desenvolvida com Tauri (Rust + WebView).

## Vantagens sobre PySide6

- **Distribuição simples**: Um único binário executável
- **Leve**: ~5MB de binário, ~50MB de RAM
- **Multiplataforma**: Linux, macOS, Windows
- **Atualizações**: Sistema de updater embutido
- **Sem dependências**: Não precisa de Python/venv no usuário final

## Instalação para desenvolvimento

### Pré-requisitos

- Node.js 18+
- Rust/Cargo (https://rustup.rs)
- Zeus instalado e funcionando

### Setup

```bash
cd desktop-tauri
npm install
```

### Desenvolvimento

```bash
npm run tauri dev
```

### Build para produção

```bash
npm run tauri build
```

O binário será gerado em `src-tauri/target/release/zeus-desktop`.

## Estrutura

```
desktop-tauri/
├── index.html          # UI principal
├── src/
│   └── main.js         # Lógica frontend
├── src-tauri/
│   ├── Cargo.toml      # Dependências Rust
│   ├── tauri.conf.json # Configuração Tauri
│   └── src/
│       └── main.rs     # Backend Rust (chama Zeus)
└── package.json
```

## Autor

Valdeir Pereira da Silva
