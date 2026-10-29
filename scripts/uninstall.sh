#!/usr/bin/env bash
set -euo pipefail

# Remove Zeus launchers and installation records created by scripts/install.sh
# and the npm package. Never touches your source checkout except its .venv
# (opt-in). State (~/.zeus) and the npm-cloned install require explicit flags.

STATE_HOME="${ZEUS_HOME:-$HOME/.zeus}"
CLONE_DIR="$HOME/.local/share/zeus-agent"
BIN_DIR="$HOME/.local/bin"
LAUNCHERS=(zeus Zeus zeus-gateway)

REMOVE_STATE=0
REMOVE_CLONE=0
REMOVE_VENV=0
SHOW_HELP=0
for arg in "$@"; do
    case "$arg" in
        --state) REMOVE_STATE=1 ;;
        --clone) REMOVE_CLONE=1 ;;
        --venv) REMOVE_VENV=1 ;;
        -h|--help) SHOW_HELP=1 ;;
        *) echo "Opção desconhecida: $arg (use --help)"; exit 1 ;;
    esac
done

if [[ $SHOW_HELP -eq 1 ]]; then
    echo "Desinstala o Zeus desta máquina (usuário atual)."
    echo "Uso: scripts/uninstall.sh [--state] [--clone] [--venv]"
    echo "     (instalado via npm: zeus-uninstall [--state] [--clone] [--venv], de qualquer diretório)"
    echo ""
    echo "Remove por padrão: launchers em ~/.local/bin e o registro ~/.zeus/install-dir."
    echo "Flags opcionais (destrutivas, pedem confirmação):"
    echo "  --state   apaga ZEUS_HOME (~/.zeus): .env com chaves, banco, memórias e histórico"
    echo "  --clone   apaga o clone npm em ~/.local/share/zeus-agent (se existir)"
    echo "  --venv    apaga o .venv do checkout onde este script vive"
    echo ""
    echo "Não remove (execute manualmente se quiser):"
    echo "  - o pacote npm global:  npm uninstall -g zeus-agent-installer"
    echo "  - serviços systemd:     sudo systemctl disable --now zeus-sandbox.service && sudo rm -f /etc/systemd/system/zeus-*.service /etc/zeus/sandbox.env /usr/local/lib/zeus/sandbox && sudo systemctl daemon-reload"
    echo "  - o checkout do código-fonte (é seu; apague com rm -rf se quiser)"
    exit 0
fi

if [[ $EUID -eq 0 ]]; then
    echo "Execute como seu usuário normal, sem sudo."
    exit 1
fi

# 1. Launchers: only remove files this installer manages.
for name in "${LAUNCHERS[@]}"; do
    target="$BIN_DIR/$name"
    if [[ -e "$target" || -L "$target" ]]; then
        if grep -Fq '# Managed by Zeus Agent installer' "$target" 2>/dev/null; then
            rm -f -- "$target"
            echo "Removido: $target"
        else
            echo "Mantido (não foi criado pelo instalador do Zeus): $target"
        fi
    fi
done

# 2. Install registry used by the npm launcher.
if [[ -f "$STATE_HOME/install-dir" ]]; then
    rm -f -- "$STATE_HOME/install-dir"
    echo "Removido: $STATE_HOME/install-dir"
fi

# 3. State directory (opt-in): credentials, database, memories, history.
if [[ $REMOVE_STATE -eq 1 ]]; then
    if [[ -d "$STATE_HOME" ]]; then
        read -r -p "Apagar $STATE_HOME (chaves de API, banco de dados, memórias e histórico)? [s/N] " answer
        if [[ "$answer" =~ ^[sS](im)?$ ]]; then
            rm -rf -- "${STATE_HOME:?}/"
            echo "Removido: $STATE_HOME"
        else
            echo "Mantido: $STATE_HOME"
        fi
    fi
fi

# 4. npm-cloned installation (opt-in).
if [[ $REMOVE_CLONE -eq 1 ]]; then
    if [[ -d "$CLONE_DIR" ]]; then
        read -r -p "Apagar o clone npm em $CLONE_DIR? [s/N] " answer
        if [[ "$answer" =~ ^[sS](im)?$ ]]; then
            rm -rf -- "${CLONE_DIR:?}/"
            echo "Removido: $CLONE_DIR"
        else
        echo "Mantido: $CLONE_DIR"
        fi
    else
        echo "Nenhum clone npm em $CLONE_DIR."
    fi
fi

# 5. Project venv (opt-in): the checkout itself stays untouched.
# When invoked from the npm global package (symlink), resolve the real
# installation via ZEUS_INSTALL_DIR or the ~/.zeus/install-dir registry
# instead of the directory the script happens to live in.
if [[ $REMOVE_VENV -eq 1 ]]; then
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [[ ! -f "$PROJECT_DIR/pyproject.toml" || ! -d "$PROJECT_DIR/zeus" ]]; then
        PROJECT_DIR="${ZEUS_INSTALL_DIR:-}"
        if [[ -z "$PROJECT_DIR" && -f "$STATE_HOME/install-dir" ]]; then
            PROJECT_DIR="$(head -n1 "$STATE_HOME/install-dir")"
        fi
        if [[ -z "$PROJECT_DIR" || ! -d "$PROJECT_DIR/.venv" ]]; then
            echo "Não consegui localizar o .venv da instalação (defina ZEUS_INSTALL_DIR ou rode dentro do checkout)."
            PROJECT_DIR=""
        fi
    fi
    if [[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR/.venv" ]]; then
        read -r -p "Apagar $PROJECT_DIR/.venv? [s/N] " answer
        if [[ "$answer" =~ ^[sS](im)?$ ]]; then
            rm -rf -- "$PROJECT_DIR/.venv"
            echo "Removido: $PROJECT_DIR/.venv"
        else
            echo "Mantido: $PROJECT_DIR/.venv"
        fi
    fi
fi

echo ""
echo "Desinstalação concluída."
echo "O pacote npm global (zeus/zeus-gateway/zeus-install), se instalado, sai com:"
echo "  npm uninstall -g zeus-agent-installer"
