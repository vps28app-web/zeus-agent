#!/usr/bin/env bash
#
# Zeus Agent Harness — Instalador
#
# Uso:
#   curl -fsSL https://SEU_SERVIDOR/install.sh | bash
#
# Ou copiar e rodar localmente:
#   bash install.sh
#
set -e

ZEUS_HOME="${ZEUS_HOME:-$HOME/.zeus}"
ZEUS_REPO="${ZEUS_REPO:-https://github.com/USER/zeus.git}"
ZEUS_BRANCH="${ZEUS_BRANCH:-main}"
INSTALL_DIR="${ZEUS_HOME}"

echo "=== Zeus Agent Harness Installer ==="
echo ""

# --- Verificar dependências ---
echo "[1/6] Verificando dependências..."

command -v python3 >/dev/null 2>&1 || { echo "Python 3 não encontrado. Instale Python 3.8+."; exit 1; }
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 8 ]]; then
    echo "Python 3.8+ necessário. Atualize seu Python."
    exit 1
fi
echo "  Python $PYTHON_VERSION OK"

# Verificar Go (opcional, só se quiser compilar sandbox)
if command -v go >/dev/null 2>&1; then
    GO_VERSION=$(go version | grep -oP 'go\d+\.\d+(\.\d+)?' | head -1)
    echo "  Go $GO_VERSION OK (opcional, para sandbox)"
fi

# Verificar git (opcional)
if ! command -v git >/dev/null 2>&1; then
    echo "  git não encontrado — instalando por zipball (sem git clone)"
    USE_GIT=0
else
    USE_GIT=1
fi

# --- Clonar ou copiar repo ---
echo "[2/6] Baixando Zeus..."

if [[ $USE_GIT -eq 1 ]]; then
    if [[ -d "$INSTALL_DIR" ]]; then
        echo "  diretório já existe — fazendo pull"
        git -C "$INSTALL_DIR" pull
    else
        git clone --depth=1 -b "$ZEUS_BRANCH" "$ZEUS_REPO" "$INSTALL_DIR"
    fi
else
    if [[ -d "$INSTALL_DIR" ]]; then
        echo "  diretório já existe — pulando download"
    else
        echo "  Baixando zipball..."
        mkdir -p "$INSTALL_DIR"
        curl -fsSL "${ZEUS_REPO%.git}/archive/refs/heads/$ZEUS_BRANCH.zip" -o /tmp/zeus.zip
        unzip -q /tmp/zeus.zip -d /tmp
        mv /tmp/zeus-*/* "$INSTALL_DIR/"
        rm -rf /tmp/zeus.zip /tmp/zeus-*
        echo "  OK"
    fi
fi

# --- Criar venv e instalar deps ---
echo "[3/6] Instalando dependências Python..."

python3 -m venv "$INSTALL_DIR/.venv"
# shellcheck disable=SC1091
source "$INSTALL_DIR/.venv/bin/activate"

pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q

echo "  .venv criado em $INSTALL_DIR/.venv"

# --- Compilar sandbox Go (se Go disponível) ---
echo "[4/6] Compilando sandbox Go..."

if command -v go >/dev/null 2>&1; then
    cd "$INSTALL_DIR/sandbox"
    GOOS=linux GOARCH=amd64 go build -o sandbox ./cmd/sandbox 2>/dev/null \
        && echo "  sandbox compilado OK" \
        || echo "  sandbox: compilação falhou (continuando sem)"
    cd "$INSTALL_DIR"
else
    echo "  Go não encontrado — sandbox não compilada"
    echo "  Para compilar manualmente: cd $INSTALL_DIR/sandbox && go build -o sandbox ./cmd/sandbox"
fi

# --- Criar arquivo .env ---
echo "[5/6] Configurando ambiente..."

ENV_FILE="$INSTALL_DIR/.env"
umask 077
if [[ -L "$ENV_FILE" ]]; then
    echo "Refusing to write credentials through a symlink: $ENV_FILE"
    exit 1
fi
if [[ -f "$ENV_FILE" ]]; then
    chmod 600 "$ENV_FILE"
fi
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" << 'EOF'
# Zeus Agent Harness — configuração
# Provedor: openrouter | ollama | opencode_go | openai | anthropic | google | deepseek | mistral
ZEUS_PROVIDER=opencode_go
ZEUS_MODEL=kimi-k2.7-code

# API keys
OPENCODE_GO_API_KEY=sk-SUA-KEY-AQUI

# Sandbox
ZEUS_SANDBOX_URL=http://127.0.0.1:9876

# Memória SQLite (true = usa SQLite, false = só JSON)
ZEUS_USE_SQLITE=true
EOF
    echo "  .env criado em $ENV_FILE"
    echo "  ATENÇÃO: edite $ENV_FILE e adicione sua API key"
else
    echo "  .env já existe — não sobrescreveu"
fi

SANDBOX_TOKEN="$("$INSTALL_DIR/.venv/bin/python" -c 'from dotenv import dotenv_values; import sys; print(dotenv_values(sys.argv[1]).get("ZEUS_SANDBOX_AUTH_TOKEN") or "")' "$ENV_FILE")"
if [[ -z "$SANDBOX_TOKEN" ]]; then
    SANDBOX_TOKEN="$("$INSTALL_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_hex(32))')"
    printf '\nZEUS_SANDBOX_AUTH_TOKEN=%s\n' "$SANDBOX_TOKEN" >> "$ENV_FILE"
fi
if [[ ! "$SANDBOX_TOKEN" =~ ^[0-9a-fA-F]{64}$ ]]; then
    echo "ZEUS_SANDBOX_AUTH_TOKEN precisa ser 64 caracteres hexadecimais (32 bytes aleatórios)."
    exit 1
fi
chmod 600 "$ENV_FILE"
unset SANDBOX_TOKEN
echo "  token de autenticação da sandbox configurado"

# --- Criar comando 'zeus' no PATH ---
echo "[6/6] Criando comando 'zeus'..."

WRAPPER="$INSTALL_DIR/.venv/bin/zeus"
cat > "$WRAPPER" << EOF
#!/bin/bash
# Zeus wrapper — auto-ativa venv e muda para ZEUS_HOME
ZEUS_HOME="${INSTALL_DIR}"
cd "\$ZEUS_HOME"
# shellcheck disable=SC1091
source "$INSTALL_DIR/.venv/bin/activate"
exec python -m zeus.cli "\$@"
EOF
chmod +x "$WRAPPER"

# Tentar criar link em ~/.local/bin (se existir e estiver no PATH)
if [[ -d "$HOME/.local/bin" ]]; then
    ln -sf "$WRAPPER" "$HOME/.local/bin/zeus" 2>/dev/null && echo "  link criado em ~/.local/bin/zeus" || true
    ln -sf "$WRAPPER" "$HOME/.local/bin/Zeus" 2>/dev/null && echo "  link criado em ~/.local/bin/Zeus" || true
    ln -sf "$WRAPPER" "$HOME/.local/bin/zeus-gateway" 2>/dev/null && echo "  link criado em ~/.local/bin/zeus-gateway" || true
    echo "  ATENÇÃO: reinicie o terminal ou rode 'hash -r' para atualizar comandos"
fi

echo ""
echo "=== Zeus instalado com sucesso! ==="
echo ""
echo "  ZEUS_HOME: $INSTALL_DIR"
echo "  comando:   $WRAPPER"
echo ""
echo "Próximos passos:"
echo "  1. Edite $ENV_FILE e adicione sua API key (o token da sandbox foi gerado)"
echo "  2. (Opcional) Compile a sandbox Go:"
echo "       cd $INSTALL_DIR/sandbox && go build -o sandbox ./cmd/sandbox"
echo "  3. (Opcional) Instale e inicie os serviços systemd (o token da sandbox foi gerado):"
echo "       sudo $INSTALL_DIR/scripts/install-systemd.sh"
echo "  4. Execute:"
echo "       $WRAPPER"
echo ""
