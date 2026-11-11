#!/usr/bin/env bash
set -euo pipefail

# Remove Zeus Desktop binary, launcher, desktop entry, and icon installed by scripts/install-desktop.sh.

STATE_HOME="${ZEUS_HOME:-$HOME/.zeus}"
PREFIX="${ZEUS_DESKTOP_PREFIX:-$HOME/.local}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

REMOVE_STATE=0
SHOW_HELP=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --state)
            REMOVE_STATE=1
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
    echo "Desinstala o Zeus Desktop da máquina atual."
    echo ""
    echo "Uso: scripts/uninstall-desktop.sh [--state] [--prefix <dir>]"
    echo ""
    echo "Remove por padrão: ~/.local/bin/zeus-desktop, ~/.local/lib/zeus-desktop,"
    echo "                   atalho .desktop e ícone SVG."
    echo "Flags opcionais:"
    echo "  --state          Remove também ~/.zeus/desktop_state.json (conversas e preferências da UI)"
    echo "  --prefix <dir>   Diretório base onde foi instalado (padrão: ~/.local)"
    exit 0
fi

if [[ $EUID -eq 0 ]]; then
    echo "Execute como seu usuário normal, sem sudo."
    exit 1
fi

LAUNCHER="$PREFIX/bin/zeus-desktop"
LIB_DIR="$PREFIX/lib/zeus-desktop"
DESKTOP_DST="$DATA_HOME/applications/zeus-desktop.desktop"
ICON_DST="$DATA_HOME/icons/hicolor/scalable/apps/zeus-desktop.svg"

if [[ -e "$LAUNCHER" || -L "$LAUNCHER" ]]; then
    if grep -Fq '# Managed by Zeus Desktop installer' "$LAUNCHER" 2>/dev/null; then
        rm -f -- "$LAUNCHER"
        echo "Removido: $LAUNCHER"
    else
        echo "Mantido (não foi criado pelo instalador do Zeus Desktop): $LAUNCHER"
    fi
fi

if [[ -d "$LIB_DIR" ]]; then
    rm -rf -- "$LIB_DIR"
    echo "Removido: $LIB_DIR"
fi

if [[ -f "$DESKTOP_DST" ]]; then
    rm -f -- "$DESKTOP_DST"
    echo "Removido: $DESKTOP_DST"
fi

if [[ -f "$ICON_DST" ]]; then
    rm -f -- "$ICON_DST"
    echo "Removido: $ICON_DST"
fi

if command -v update-desktop-database >/dev/null 2>&1 && [[ -d "$DATA_HOME/applications" ]]; then
    update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
fi

if [[ $REMOVE_STATE -eq 1 && -f "$STATE_HOME/desktop_state.json" ]]; then
    read -r -p "Apagar $STATE_HOME/desktop_state.json (conversas e preferências do Desktop)? [s/N] " answer
    if [[ "$answer" =~ ^[sS](im)?$ ]]; then
        rm -f -- "$STATE_HOME/desktop_state.json"
        echo "Removido: $STATE_HOME/desktop_state.json"
    else
        echo "Mantido: $STATE_HOME/desktop_state.json"
    fi
fi

echo "Desinstalação do Zeus Desktop concluída."
