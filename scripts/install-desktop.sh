#!/usr/bin/env bash
set -euo pipefail

# Install Zeus Desktop (Rust native egui/eframe client) and ensure the Zeus Core
# Python base is installed for the current user. Does not require sudo.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$PROJECT_DIR/desktop"
STATE_HOME="${ZEUS_HOME:-$HOME/.zeus}"
PREFIX="${ZEUS_DESKTOP_PREFIX:-$HOME/.local}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

NO_BUILD=0
SKIP_CORE=0
FORCE_CORE=0
SHOW_HELP=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-build)
            NO_BUILD=1
            shift
            ;;
        --skip-core)
            SKIP_CORE=1
            shift
            ;;
        --with-core)
            FORCE_CORE=1
            shift
            ;;
        --prefix)
            if [[ $# -lt 2 ]]; then
                echo "Erro: --prefix requer um diretório."
                exit 1
            fi
            PREFIX="$2"
            shift 2
            ;;
        -h|--help)
            SHOW_HELP=1
            shift
            ;;
        *)
            echo "Opção desconhecida: $1 (use --help)"
            exit 1
            ;;
    esac
done

if [[ $SHOW_HELP -eq 1 ]]; then
    echo "Instala o Zeus Desktop (Rust nativo) junto com a base Zeus Core para o usuário atual."
    echo ""
    echo "Uso: scripts/install-desktop.sh [opções]"
    echo ""
    echo "Por padrão, verifica se o Zeus Core (.venv + pacote zeus) está instalado e"
    echo "executa scripts/install.sh automaticamente caso ainda não esteja."
    echo ""
    echo "Opções:"
    echo "  --no-build       Usa o binário release já compilado em desktop/target/release/zeus-desktop"
    echo "  --with-core      Força a reinstalação da base Python (scripts/install.sh) mesmo se já existir"
    echo "  --skip-core      Pula a verificação/instalação da base Zeus Core (avançado)"
    echo "  --prefix <dir>   Diretório base de instalação (padrão: ~/.local)"
    echo "  -h, --help       Exibe esta ajuda"
    exit 0
fi

if [[ $EUID -eq 0 ]]; then
    echo "Execute este instalador como seu usuário normal, sem sudo."
    exit 1
fi

if [[ ! -f "$DESKTOP_DIR/Cargo.toml" || ! -d "$PROJECT_DIR/zeus" ]]; then
    echo "Execute scripts/install-desktop.sh a partir de um checkout válido do Zeus."
    exit 1
fi

if [[ "$STATE_HOME" != /* ]]; then
    echo "ZEUS_HOME deve ser um caminho absoluto: $STATE_HOME"
    exit 1
fi

if [[ "$PREFIX" != /* ]]; then
    echo "--prefix deve ser um caminho absoluto: $PREFIX"
    exit 1
fi

if [[ -L "$STATE_HOME" ]]; then
    echo "Recusando usar symlink como ZEUS_HOME: $STATE_HOME"
    exit 1
fi

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"

if [[ $SKIP_CORE -eq 0 ]]; then
    CORE_READY=0
    if [[ $FORCE_CORE -eq 0 && -x "$VENV_PYTHON" ]]; then
        if "$VENV_PYTHON" -c "import zeus.cli" >/dev/null 2>&1; then
            CORE_READY=1
        fi
    fi

    if [[ $CORE_READY -eq 0 ]]; then
        echo "==> Base do Zeus Core não encontrada ou desatualizada. Instalando via scripts/install.sh..."
        ZEUS_HOME="$STATE_HOME" "$PROJECT_DIR/scripts/install.sh"
    else
        echo "==> Base do Zeus Core verificada: $VENV_PYTHON"
    fi

    if [[ ! -x "$VENV_PYTHON" ]] || ! "$VENV_PYTHON" -c "import zeus.cli" >/dev/null 2>&1; then
        echo "Erro: a base do Zeus Core não ficou disponível em $VENV_PYTHON."
        exit 1
    fi
fi

RELEASE_BIN="$DESKTOP_DIR/target/release/zeus-desktop"

if [[ $NO_BUILD -eq 0 || ! -x "$RELEASE_BIN" ]]; then
    if ! command -v cargo >/dev/null 2>&1; then
        if [[ -x "$HOME/.cargo/bin/cargo" ]]; then
            export PATH="$HOME/.cargo/bin:$PATH"
        else
            echo "Cargo/Rust não encontrado. Instale via rustup: https://rustup.rs"
            exit 1
        fi
    fi

    echo "==> Compilando Zeus Desktop (release)..."
    cargo build --release --manifest-path "$DESKTOP_DIR/Cargo.toml"
else
    echo "==> Usando binário release existente: $RELEASE_BIN"
fi

if [[ ! -x "$RELEASE_BIN" ]]; then
    echo "Binário não encontrado após compilação: $RELEASE_BIN"
    exit 1
fi

BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/lib/zeus-desktop"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$LIB_DIR" "$APPS_DIR" "$ICON_DIR" "$STATE_HOME"

# Instalar binário de forma atômica
TARGET_BIN="$LIB_DIR/zeus-desktop"
BIN_TMP="$(mktemp "$LIB_DIR/.zeus-desktop.XXXXXX")"
trap 'rm -f -- "$BIN_TMP"' EXIT
cp "$RELEASE_BIN" "$BIN_TMP"
chmod 755 "$BIN_TMP"
mv -f "$BIN_TMP" "$TARGET_BIN"
trap - EXIT

# Instalar launcher gerenciado em ~/.local/bin/zeus-desktop
LAUNCHER="$BIN_DIR/zeus-desktop"
if [[ -e "$LAUNCHER" || -L "$LAUNCHER" ]]; then
    if ! grep -Fq '# Managed by Zeus Desktop installer' "$LAUNCHER" 2>/dev/null; then
        echo "AVISO: Comando existente não gerenciado mantido inalterado: $LAUNCHER"
    else
        write_launcher=1
    fi
else
    write_launcher=1
fi

if [[ "${write_launcher:-0}" -eq 1 ]]; then
    LAUNCHER_TMP="$(mktemp "$BIN_DIR/.zeus-desktop.XXXXXX")"
    trap 'rm -f -- "$LAUNCHER_TMP"' EXIT
    {
        printf '#!/usr/bin/env bash\n'
        printf '# Managed by Zeus Desktop installer\n'
        printf 'export ZEUS_DIR="${ZEUS_DIR:-%s}"\n' "$PROJECT_DIR"
        printf 'export ZEUS_HOME="${ZEUS_HOME:-%s}"\n' "$STATE_HOME"
        printf 'if [[ -z "${ZEUS_PYTHON:-}" && -x "%s/.venv/bin/python3" ]]; then\n' "$PROJECT_DIR"
        printf '    export ZEUS_PYTHON="%s/.venv/bin/python3"\n' "$PROJECT_DIR"
        printf 'fi\n'
        printf 'exec "%s" "$@"\n' "$TARGET_BIN"
    } > "$LAUNCHER_TMP"
    chmod 755 "$LAUNCHER_TMP"
    mv -f "$LAUNCHER_TMP" "$LAUNCHER"
    trap - EXIT
fi

# Instalar ícone SVG
ICON_SRC="$DESKTOP_DIR/assets/zeus-desktop.svg"
ICON_DST="$ICON_DIR/zeus-desktop.svg"
if [[ -f "$ICON_SRC" ]]; then
    cp "$ICON_SRC" "$ICON_DST"
    chmod 644 "$ICON_DST"
fi

# Instalar entrada .desktop com caminho absoluto no Exec=
DESKTOP_DST="$APPS_DIR/zeus-desktop.desktop"
DESKTOP_TMP="$(mktemp "$APPS_DIR/.zeus-desktop.desktop.XXXXXX")"
trap 'rm -f -- "$DESKTOP_TMP"' EXIT
cat > "$DESKTOP_TMP" <<EOF
[Desktop Entry]
Name=Zeus Desktop
Comment=Interface gráfica nativa de alto desempenho para o Zeus Agent
Exec=$LAUNCHER
Icon=zeus-desktop
Terminal=false
Type=Application
Categories=Development;Utility;
Keywords=AI;Agent;Coding;Zeus;
StartupWMClass=zeus-desktop
EOF
chmod 644 "$DESKTOP_TMP"
mv -f "$DESKTOP_TMP" "$DESKTOP_DST"
trap - EXIT

# Atualizar caches XDG se disponíveis
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

echo ""
echo "Zeus Desktop instalado com sucesso!"
echo "  Base Core:   $VENV_PYTHON"
echo "  Binário:     $TARGET_BIN"
echo "  Launcher:    $LAUNCHER"
echo "  Atalho menu: $DESKTOP_DST"
if [[ -f "$ICON_DST" ]]; then
    echo "  Ícone:       $ICON_DST"
fi
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        echo ""
        echo "Adicione $BIN_DIR ao seu PATH para executar 'zeus-desktop' diretamente no terminal."
        ;;
esac
