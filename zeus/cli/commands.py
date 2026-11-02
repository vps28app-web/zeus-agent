"""Slash command handlers and interactive menus for Zeus CLI."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from zeus.cli.renderer import _color, _get_term_width


def _load_env(override: bool = False) -> None:
    """Load .env from ~/.zeus/.env or the project root if present."""
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    paths = [zeus_home / ".env", Path.cwd() / ".env"]
    install_dir = os.getenv("ZEUS_INSTALL_DIR")
    if install_dir:
        paths.append(Path(install_dir) / ".env")
    for env_file in paths:
        if env_file.exists():
            load_dotenv(env_file, override=override)

    # Sync GEMINI_API_KEY and GOOGLE_API_KEY aliases
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
        os.environ["GOOGLE_API_KEY"] = gemini_key


def _set_zeus_env(key: str, value: str) -> None:
    """Update an env variable both in the current process and in ~/.zeus/.env."""
    os.environ[key] = value
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    env_file = zeus_home / ".env"

    lines: List[str] = []
    if env_file.exists():
        with env_file.open("r", encoding="utf-8") as f:
            lines = f.readlines()

    found = False
    new_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} =") or stripped.startswith(f"#{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    zeus_home.mkdir(parents=True, exist_ok=True)
    with env_file.open("w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _dispatch_set_zeus_env(key: str, value: str) -> None:
    main_mod = sys.modules.get("zeus.cli.main")
    fn = getattr(main_mod, "_set_zeus_env", None) if main_mod else None
    if fn and fn is not _dispatch_set_zeus_env:
        fn(key, value)
    else:
        _set_zeus_env(key, value)


def _dispatch_load_env(override: bool = False) -> None:
    main_mod = sys.modules.get("zeus.cli.main")
    fn = getattr(main_mod, "_load_env", None) if main_mod else None
    if fn and fn is not _dispatch_load_env:
        fn(override=override)
    else:
        _load_env(override=override)


def _current_skill_label(active_filter: Optional[set]) -> str:
    from zeus.cli.main import SKILL_SETS

    if not active_filter:
        return "all"
    for key, cfg in SKILL_SETS.items():
        if cfg["tags"] == active_filter:
            return key
    return "custom"


def _print_skills_menu(active_filter: Optional[set]) -> None:
    """Print a visual menu of available skill sets."""
    from zeus.cli.main import SKILL_SETS

    term_width = _get_term_width()
    title = " 🧛 SKILL SETS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Personas disponíveis (restringe ferramentas visíveis):', 90)}")
    print(f"{_color('│', 33)}")

    current_label = _current_skill_label(active_filter)

    for key, cfg in SKILL_SETS.items():
        is_active = (key == current_label)
        marker = _color("● ATIVO", 32) if is_active else _color("○", 90)
        label = _color(cfg["label"], "1;37" if is_active else 37)
        cmd = _color(f"/skills {key}", "1;33" if is_active else 33)
        print(f"{_color('│', 33)}  {marker} {cmd}  {label}")
        print(f"{_color('│', 33)}     {_color(cfg['description'], 90)}")

    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('Use /skills <nome> para ativar um skill set.', 90)}")
    print(bottom)
    print()


def _print_command_menu() -> None:
    """Print a visual menu of available slash commands."""
    term_width = _get_term_width()
    title = " ⚡ MENU DE COMANDOS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    commands = [
        ("/new", "Cria uma nova sessão (novo ID)"),
        ("/reset", "Reseta a sessão atual (mantém ID, zera métricas)"),
        ("/clear", "Limpa a tela"),
        ("/summary", "Mostra resumo da sessão"),
        ("/skills", "Seleciona um skill set/persona para filtrar ferramentas"),
        ("/auth", "Autentica Google Gemini via browser (provider google_auth)"),
        ("/mcp", "Gerencia servidores Model Context Protocol (MCP)"),
        ("/config", "Gerencia configurações do Zeus (get/set/list)"),
        ("/learn", "Aprendizados passados (list/search/add/stats/forget)"),
        ("/brain", "Dashboard de inteligência e aprendizado contínuo"),
        ("/models", "Troca o provedor e modelo LLM"),
        ("/mode <sandbox|terminal|auto|dryrun|readonly>", "Alterna modo de execução e segurança"),
        ("/mode file <read_only|project_only|unrestricted>", "Define permissão de arquivo"),
        ("/mode status", "Mostra apenas o status atual do agente"),
        ("/plan <tarefa>", "Cria e executa um plano passo a passo"),
        ("/plan bmad <ideia>", "Análise BMAD de modelo de negócio"),
        ("/team <tarefa>", "Executa com equipe multi-agente"),
        ("/help", "Mostra este menu"),
        ("/exit", "Encerra o Zeus"),
    ]

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Digite /comando ou escolha abaixo:', 90)}")
    print(f"{_color('│', 33)}")
    max_cmd = max(len(cmd) for cmd, _ in commands)
    for cmd, desc in commands:
        pad = " " * (max_cmd - len(cmd))
        print(f"{_color('│', 33)}  {_color(cmd, '1;33')}{pad}  {desc}")
    print(bottom)
    print()


def _print_mcp_menu() -> None:
    """Print status of configured MCP servers and active tools."""
    from zeus.mcp import get_mcp_manager
    mgr = get_mcp_manager()
    statuses = mgr.list_status()

    term_width = _get_term_width()
    title = " 🔌 MODEL CONTEXT PROTOCOL (MCP) "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    if not statuses:
        print(f"{_color('│', 33)}  {_color('Nenhum servidor MCP configurado.', 90)}")
        print(f"{_color('│', 33)}  {_color('Adicione um servidor:', 90)} /mcp add <nome> <comando_ou_url> [args...]")
    else:
        for srv in statuses:
            status_symbol = _color("● Ativo", 32) if srv["active"] else _color("○ Inativo", 31)
            type_label = _color(f"[{srv['type'].upper()}]", 36)
            cmd = _color(srv["command_or_url"], 90)
            tools_info = _color(f"({srv['tool_count']} ferramentas)", 33) if srv["active"] else ""
            print(f"{_color('│', 33)}  {status_symbol} {_color(srv['name'], '1;37')} {type_label} - {cmd}  {tools_info}")

    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('Comandos MCP:', 90)}")
    print(f"{_color('│', 33)}    • {_color('/mcp list', 33)}                        - Lista servidores e status")
    print(f"{_color('│', 33)}    • {_color('/mcp add <nome> <cmd|url> [args]', 33)} - Adiciona e conecta novo servidor")
    print(f"{_color('│', 33)}    • {_color('/mcp remove <nome>', 33)}              - Remove um servidor MCP")
    print(f"{_color('│', 33)}    • {_color('/mcp reload', 33)}                     - Reconecta todos os servidores")
    print(bottom)
    print()


def _handle_mcp_command(text: str) -> None:
    """Handle /mcp subcommands."""
    from zeus.mcp import get_mcp_manager
    mgr = get_mcp_manager()
    parts = text.split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "ls", "status"):
        _print_mcp_menu()
    elif subcmd == "reload":
        print(f"\n{_color('🔄 Reconectando servidores MCP...', 33)}")
        res = mgr.reload()
        for name, ok in res.items():
            status = _color("Conectado", 32) if ok else _color("Falhou", 31)
            print(f"  • {name}: {status}")
        print()
    elif subcmd in ("remove", "rm", "delete"):
        if len(parts) < 3:
            print(f"\n{_color('❌ Uso:', '1;31')} /mcp remove <nome_do_servidor>\n")
            return
        name = parts[2]
        if mgr.remove_server(name):
            print(f"\n{_color('✅ Servidor MCP removido:', 32)} {name}\n")
        else:
            print(f"\n{_color('❌ Servidor MCP não encontrado:', '1;31')} {name}\n")
    elif subcmd in ("add", "connect"):
        if len(parts) < 3:
            print(f"\n{_color('❌ Uso:', '1;31')} /mcp add <nome> [comando_ou_url] [args...]")
            print(f"{_color('Exemplo (Preset):', 90)} /mcp add gemini")
            print(f"{_color('Exemplo (Custom):', 90)} /mcp add meuteste npx -y @modelcontextprotocol/server-memory\n")
            return
        name = parts[2]
        cmd_or_url = parts[3] if len(parts) > 3 else name
        args = parts[4:] if len(parts) > 4 else []
        print(f"\n{_color('🔌 Conectando servidor MCP:', 33)} {name}...")
        try:
            ok = mgr.add_server(name, cmd_or_url, args=args)
        except Exception as exc:
            ok = False
            print(f"{_color('❀ Detalhes técnicos:', 90)} {exc}")
        if ok:
            client = mgr.clients.get(name)
            tool_cnt = len(client.tools) if client else 0
            print(f"{_color('✅ Conectado com sucesso!', 32)} {tool_cnt} ferramentas disponíveis.\n")
        else:
            print(f"{_color('❌ Falha ao conectar ao servidor MCP.', '1;31')}\n")
    else:
        _print_mcp_menu()


def _print_brain_dashboard() -> None:
    """Print continuous learning and intelligence statistics dashboard."""
    from zeus.memory.learning import LearningStore
    from zeus.memory.reasoning import ReasoningMemory
    from zeus.memory.store import MemoryStore
    from zeus.memory.user_profile import UserProfileStore

    l_store = LearningStore()
    l_stats = l_store.get_stats()

    m_store = MemoryStore()
    m_keys = m_store.keys()

    p_store = UserProfileStore()
    profiles = p_store.list_profiles()

    r_mem = ReasoningMemory()
    r_entries = r_mem.recall("", limit=100)

    term_width = _get_term_width()
    title = " 🧠 ZEUS CONTINUOUS LEARNING & BRAIN DASHBOARD "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 36) + _color(title, "1;36") + _color("─" * line_length, 36)
    bottom = _color("╰" + "─" * (term_width - 3), 36)

    print()
    print(top)
    print(f"{_color('│', 36)}  {_color('📊 Padrões Aprendidos (Continuous Learning Store):', '1;37')}")
    print(f"{_color('│', 36)}    • Total de Aprendizados: {_color(str(l_stats['total_learnings']), 33)}")
    print(f"{_color('│', 36)}    • Auto-Aprendidos em Sessões: {_color(str(l_stats['auto_learned']), 32)}")
    print(f"{_color('│', 36)}    • Alta Relevância (Score > 0): {_color(str(l_stats['high_effectiveness']), 32)}")
    if l_stats["tags_summary"]:
        tags_str = ", ".join(f"{k}:{v}" for k, v in list(l_stats["tags_summary"].items())[:6])
        print(f"{_color('│', 36)}    • Tags Principais: {_color(tags_str, 90)}")

    print(f"{_color('│', 36)}")
    print(f"{_color('│', 36)}  {_color('💡 Raciocínios e Estratégias Salvas (Reasoning Memory):', '1;37')}")
    print(f"{_color('│', 36)}    • Padrões de Raciocínio: {_color(str(len(r_entries)), 33)}")

    print(f"{_color('│', 36)}")
    print(f"{_color('│', 36)}  {_color('👤 Conhecimento sobre Usuário & Perfil:', '1;37')}")
    print(f"{_color('│', 36)}    • Perfis Ativos: {_color(str(len(profiles)), 33)}")
    print(f"{_color('│', 36)}    • Chaves de Conhecimento Persistente: {_color(str(len(m_keys)), 33)}")

    print(f"{_color('│', 36)}")
    print(f"{_color('│', 36)}  {_color('⚡ O Zeus aprende autonomamente após resoluções e avalia feedback do usuário!', 90)}")
    print(bottom)
    print()


def _print_learning_menu() -> None:
    """Print a visual menu for the /learn command."""
    term_width = _get_term_width()
    title = " 📚 APRENDIZADOS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Comandos:', 90)}")
    print(f"{_color('│', 33)}    • {_color('/learn', 33)}                       - Menu de aprendizados")
    print(f"{_color('│', 33)}    • {_color('/learn list', 33)}                  - Lista recentes")
    print(f"{_color('│', 33)}    • {_color('/learn search <query>', 33)}        - Busca aprendizados por palavra-chave")
    print(f"{_color('│', 33)}    • {_color('/learn add <p> | <s> [tags]', 33)} - Adiciona aprendizado manual")
    print(f"{_color('│', 33)}    • {_color('/learn rate <id> <+1/-1>', 33)}    - Avalia aprendizado")
    print(f"{_color('│', 33)}    • {_color('/learn stats', 33)}                 - Dashboard de inteligência / brain")
    print(f"{_color('│', 33)}    • {_color('/learn forget <id>', 33)}            - Remove aprendizado específico")
    print(bottom)
    print()


def _handle_learning_command(text: str) -> None:
    """Handle /learn subcommands."""
    from zeus.memory.learning import LearningStore

    parts = text.split(maxsplit=1)
    subcmd = parts[1].lower().strip() if len(parts) > 1 else "menu"

    store = LearningStore()

    if subcmd == "menu" or subcmd == "":
        _print_learning_menu()
        return

    if subcmd in ("stats", "brain", "dashboard"):
        _print_brain_dashboard()
        return

    if subcmd == "list":
        learnings = store.list_recent(limit=10)
        print(f"\n{_color('📚 Aprendizados recentes:', 33)}")
        if not learnings:
            print(f"  {_color('Nenhum aprendizado registrado ainda.', 90)}")
        for item in learnings:
            score = item.get("effectiveness_score", 0)
            score_color = 32 if score > 0 else 31 if score < 0 else 90
            item_id = item.get("id")
            item_problem = item.get("problem", "")[:60]
            item_tags = ", ".join(item.get("tags", []))
            print(f"  {_color(f'[{item_id}]', '1;33')} {item_problem}")
            print(f"    {_color('Score:', score_color)} {score} {_color('Tags:', 90)} {item_tags}")
        print()
        return

    if subcmd.startswith("search "):
        query = subcmd[len("search "):].strip()
        results = store.search(query, limit=5)
        print(f"\n{_color('🔍 Resultados:', 33)} {query}\n")
        if not results:
            print(f"  {_color('Nenhum aprendizado encontrado para essa busca.', 90)}")
        for item in results:
            item_id = item.get("id")
            item_problem = item.get("problem", "")
            item_solution = item.get("solution", "")[:120]
            print(f"  {_color(f'[{item_id}]', '1;33')} {item_problem}")
            print(f"    {_color('Solução:', 90)} {item_solution}")
        print()
        return

    if subcmd.startswith("add "):
        payload = subcmd[len("add "):].strip()
        if "|" not in payload:
            print(f"\n{_color('❌ Uso:', '1;31')} /learn add <problema> | <solução> [tags:tag1,tag2]\n")
            return
        problem, rest = payload.split("|", 1)
        solution = rest.strip()
        tags = []
        if "tags:" in solution:
            solution, tags_str = solution.rsplit("tags:", 1)
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        learning_id = store.save(
            problem=problem.strip(),
            solution=solution.strip(),
            tags=list(set(tags + ["manual"])),
            effectiveness_score=2,
        )
        print(f"\n{_color('✅ Aprendizado salvo:', 32)} ID {learning_id}\n")
        return

    if subcmd.startswith("rate "):
        rest = subcmd[len("rate "):].strip()
        tokens = rest.split()
        if len(tokens) < 2 or not tokens[0].isdigit() or tokens[1] not in ("+1", "-1"):
            print(f"\n{_color('❌ Uso:', '1;31')} /learn rate <id> <+1/-1>\n")
            return
        learning_id = int(tokens[0])
        helpful = tokens[1] == "+1"
        store.rate(learning_id, helpful)
        print(f"\n{_color('✅ Feedback registrado:', 32)} ID {learning_id} {'+1' if helpful else '-1'}\n")
        return

    if subcmd.startswith("forget ") or subcmd.startswith("delete "):
        rest = subcmd.split(maxsplit=1)[1].strip()
        if not rest.isdigit():
            print(f"\n{_color('❌ Uso:', '1;31')} /learn forget <id>\n")
            return
        learning_id = int(rest)
        store.delete(learning_id)
        print(f"\n{_color('✅ Aprendizado removido:', 32)} ID {learning_id}\n")
        return

    _print_learning_menu()


def _print_config_menu(config: Dict[str, Any]) -> None:
    """Print current Zeus configuration in a visual card."""
    term_width = _get_term_width()
    title = " ⚙️ CONFIGURAÇÃO ZEUS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Provider:', 90)} {config.get('zeus_provider', 'unknown')}")
    print(f"{_color('│', 33)}  {_color('Model:', 90)}    {config.get('zeus_model', 'unknown')}")
    print(f"{_color('│', 33)}  {_color('Max turns:', 90)} {config.get('max_turns', 'unknown')}")
    print(f"{_color('│', 33)}  {_color('Config file:', 90)} {config.get('config_file', 'unknown')}")
    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('API Keys:', 90)}")
    for key, value in config.get("api_keys_status", {}).items():
        print(f"{_color('│', 33)}    • {_color(key, '1;37')}: {value}")
    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('Comandos:', 90)}")
    print(f"{_color('│', 33)}    • {_color('/config', 33)}                  - Mostra configuração atual")
    print(f"{_color('│', 33)}    • {_color('/config get <key>', 33)}      - Lê valor de uma variável")
    print(f"{_color('│', 33)}    • {_color('/config set <key> <value>', 33)} - Define variável não secreta no .env ou config.yaml")
    print(f"{_color('│', 33)}    • {_color('/config set OPENCODE_GO_API_KEY', 33)} - Define/troca a chave via prompt mascarado")
    print(f"{_color('│', 33)}    • {_color('/config set max_turns <n>', 33)} - Define limite de turnos do agente")
    print(f"{_color('│', 33)}    • {_color('/config list-models [provider]', 33)} - Lista modelos disponíveis")
    print(bottom)
    print()


def _handle_config_command(text: str) -> None:
    """Handle /config subcommands."""
    from zeus.tools.config_tools import get_zeus_config, list_available_models, update_zeus_config

    parts = text.split(maxsplit=2)
    subcmd = parts[1].lower() if len(parts) > 1 else "show"

    if subcmd in ("show", "get", "list"):
        if subcmd == "get" and len(parts) >= 3:
            key = parts[2].strip().upper()
            value = os.getenv(key)
            if value is None:
                print(f"\n{_color('❌', '1;31')} {key}: não configurado\n")
            else:
                is_secret = any(
                    token in key
                    for token in ("TOKEN", "KEY", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")
                )
                if is_secret:
                    status = f"{_color('Configurado:', 32)} {'*' * max(4, len(value) - 4)}{value[-4:] if len(value) > 4 else ''}"
                else:
                    status = f"{_color('Configurado:', 32)} {value}"
                print(f"\n{_color('🔑', 33)} {key}: {status}\n")
        elif subcmd == "list" and len(parts) >= 3:
            provider = parts[2].strip()
            models = list_available_models(provider)
            if "error" in models:
                print(f"\n{_color('❌', '1;31')} {models['error']}\n")
            else:
                print(f"\n{_color('🤖 Modelos', 33)} {_color(provider, '1;33')}:")
                for m in models.get("models", []):
                    print(f"  • {m}")
                print()
        else:
            _print_config_menu(get_zeus_config())

    elif subcmd in ("set", "update"):
        if len(parts) < 3:
            print(f"\n{_color('❌ Uso:', '1;31')} /config set <KEY> <value>\n")
            return
        values = parts[2].split(maxsplit=1)
        key = values[0].strip().upper()
        is_secret = any(
            token in key
            for token in ("TOKEN", "KEY", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")
        )
        if len(values) == 1:
            if not is_secret:
                print(f"\n{_color('❌ Uso:', '1;31')} /config set <KEY> <value>\n")
                return
            from zeus.cli.setup_commands import _get_input
            value = _get_input(f"{key} (entrada mascarada)", secret=True)
            if not value:
                print(f"\n{_color('Configuração cancelada.', 33)}\n")
                return
        else:
            if is_secret:
                print(
                    f"\n{_color('Por segurança:', 33)} use /config set {key} sem informar o valor; "
                    "a próxima entrada será mascarada.\n"
                )
                return
            value = values[1]

        result = update_zeus_config(key, value)
        if result.get("status") == "success":
            print(f"\n{_color('✅ Configuração salva:', 32)} {result['key']} = {result['new_value_masked']}\n")
            if result['key'] in ("ZEUS_PROVIDER", "ZEUS_MODEL"):
                _dispatch_load_env(override=True)
                print(f"{_color('🔄 Sessão atual recarregada:', 33)} provider={os.getenv('ZEUS_PROVIDER')} model={os.getenv('ZEUS_MODEL')}\n")
        else:
            print(f"\n{_color('❌ Erro:', '1;31')} {result.get('error', 'unknown')}\n")

    else:
        _print_config_menu(get_zeus_config())


def _print_mode_menu(show_commands: bool = True) -> None:
    """Print current execution mode and available options in a status card."""
    from zeus.security.permissions import PermissionManager

    pm = PermissionManager()
    exec_mode = pm.exec_level
    file_mode = pm.file_level
    runtime_mode = pm.execution_mode
    dry_run = pm.dry_run

    term_width = _get_term_width()
    title = " STATUS DO AGENTE "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)
    sep = _color("│" + "─" * (term_width - 3), 33)

    if exec_mode == "sandbox":
        exec_label = f"{_color('●', 32)} {_color('SANDBOX', '1;32')}"
        exec_detail = "Restringe comandos ao sandbox"
    elif runtime_mode == "auto":
        exec_label = f"{_color('●', 35)} {_color('AUTO', '1;35')}"
        exec_detail = "Executa comandos automaticamente"
    else:
        exec_label = f"{_color('●', 33)} {_color('TERMINAL', '1;33')} ({_color('Manual', 37)})"
        exec_detail = "Permite comandos com confirmação"

    file_labels = {
        "read_only": f"{_color('Apenas Leitura', 32)}",
        "project_only": f"{_color('Projeto Apenas', 33)}",
        "unrestricted": f"{_color('Total', 31)}",
    }
    file_label = file_labels.get(file_mode, file_mode)

    dry_label = _color("ATIVADO", 36) if dry_run else _color("DESATIVADO", 90)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Modo de Execução:', 90)}    {exec_label}")
    print(f"{_color('│', 33)}  {_color('Permissão de Arquivos:', 90)} {file_label}")
    print(f"{_color('│', 33)}  {_color('Simulação (Dry-run):', 90)} {dry_label}")
    if show_commands:
        print(sep)
        print(f"{_color('│', 33)}  {_color('COMANDOS DE CONFIGURAÇÃO', '1;37')}")
        print(f"{_color('│', 33)}  • {_color('/mode status', 33)}    - Mostra apenas o status atual")
        print(f"{_color('│', 33)}  • {_color('/mode sandbox', 33)}   - {exec_detail if exec_mode == 'sandbox' else 'Restringe comandos ao sandbox'}")
        print(f"{_color('│', 33)}  • {_color('/mode terminal', 33)}  - Permite comandos com confirmação")
        print(f"{_color('│', 33)}  • {_color('/mode auto', 33)}      - Executa comandos automaticamente")
        print(f"{_color('│', 33)}  • {_color('/mode dryrun', 33)}    - Apenas simula as ações")
        print(f"{_color('│', 33)}  • {_color('/mode file <read_only|project_only|unrestricted>', 33)}")
    print(bottom)
    print()


def _handle_mode_command(text: str) -> None:
    """Handle /mode subcommands to switch execution permission and runtime mode."""
    from zeus.security.permissions import PermissionManager, get_global_permission_manager

    parts = text.split(maxsplit=1)
    subcmd = parts[1].lower().strip() if len(parts) > 1 else ""

    pm = PermissionManager()
    _ = pm

    if subcmd in ("", "menu"):
        _print_mode_menu(show_commands=True)
        return

    if subcmd == "status":
        _print_mode_menu(show_commands=False)
        return

    pm = get_global_permission_manager()

    if subcmd in ("sandbox", "safe"):
        _dispatch_set_zeus_env("ZEUS_EXECUTION_PERMISSION", "sandbox_only")
        _dispatch_set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _dispatch_set_zeus_env("ZEUS_DRY_RUN", "0")
        _dispatch_set_zeus_env("ZEUS_READ_ONLY", "0")
        pm.set_exec_level("sandbox_only")
        print(f"\n{_color('🛡️  Modo sandbox ativado.', 32)}")
        print(f"{_color('   Terminal do host bloqueado.', 90)}\n")
        return

    if subcmd in ("terminal", "host"):
        _dispatch_set_zeus_env("ZEUS_EXECUTION_PERMISSION", "allow")
        _dispatch_set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _dispatch_set_zeus_env("ZEUS_DRY_RUN", "0")
        _dispatch_set_zeus_env("ZEUS_READ_ONLY", "0")
        pm.set_exec_level("allow")
        print(f"\n{_color('⚡ Modo terminal ativado.', 33)}")
        print(f"{_color('   run_terminal liberado com confirmação humana.', 90)}")
        print(f"{_color('   Comandos de alto risco pedirão aprovação.', 31)}\n")
        return

    if subcmd == "auto":
        _dispatch_set_zeus_env("ZEUS_EXECUTION_PERMISSION", "allow")
        _dispatch_set_zeus_env("ZEUS_EXECUTION_MODE", "auto")
        _dispatch_set_zeus_env("ZEUS_DRY_RUN", "0")
        _dispatch_set_zeus_env("ZEUS_READ_ONLY", "0")
        pm.set_exec_level("allow")
        print(f"\n{_color('🚀 Modo automático ativado.', 35)}")
        print(f"{_color('   run_terminal executa sem confirmação.', 90)}")
        print(f"{_color('   Apenas o resultado é apresentado.', 90)}\n")
        return

    if subcmd == "dryrun":
        _dispatch_set_zeus_env("ZEUS_EXECUTION_PERMISSION", "allow")
        _dispatch_set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _dispatch_set_zeus_env("ZEUS_DRY_RUN", "1")
        _dispatch_set_zeus_env("ZEUS_READ_ONLY", "0")
        print(f"\n{_color('👁️  Modo dry-run ativado.', 36)}")
        print(f"{_color('   Ferramentas mutantes são apenas simuladas.', 90)}\n")
        return

    if subcmd == "readonly":
        _dispatch_set_zeus_env("ZEUS_EXECUTION_PERMISSION", "deny")
        _dispatch_set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _dispatch_set_zeus_env("ZEUS_DRY_RUN", "0")
        _dispatch_set_zeus_env("ZEUS_READ_ONLY", "1")
        print(f"\n{_color('🔍 Modo somente leitura ativado.', 34)}")
        print(f"{_color('   Apenas ferramentas de leitura estão liberadas.', 90)}\n")
        return

    if subcmd.startswith("file "):
        level = subcmd[len("file "):].strip()
        if level not in PermissionManager.FILE_LEVELS:
            print(f"\n{_color('❌ Nível de arquivo inválido:', '1;31')} {level}")
            print(f"{_color('Use:', 90)} /mode file read_only | project_only | unrestricted\n")
            return
        _dispatch_set_zeus_env("ZEUS_FILE_PERMISSION", level)
        print(f"\n{_color('📁  Permissão de arquivo:', 32)} {level}\n")
        return

    print(f"\n{_color('❌ Modo desconhecido:', '1;31')} {subcmd}")
    print(f"{_color('Use:', 90)} /mode sandbox | terminal | auto | dryrun | readonly | file <nível>\n")


def _handle_auth_command(text: str) -> None:
    """Handle /auth subcommands for Google OAuth (authorization code flow)."""
    from zeus.core.google_oauth_desktop import (
        has_valid_credentials,
        revoke_credentials,
        start_authorization_flow,
    )

    parts = text.split()
    subcmd = parts[1].lower() if len(parts) > 1 else "google"

    if subcmd == "google":
        provider = os.getenv("ZEUS_PROVIDER", "")
        if provider != "google_auth":
            aviso = "\n" + _color("Aviso:", "1;33")
            print(
                f"{aviso} ZEUS_PROVIDER='{provider}'. "
                f"Para usar OAuth defina: {_color('/config set ZEUS_PROVIDER google_auth', 36)}\n"
            )
        print(f"\n{_color('Iniciando login do Google no navegador...', 33)}\n")
        try:
            credentials = start_authorization_flow()
            masked = credentials['access_token'][-8:] if len(credentials['access_token']) > 8 else ""
            ok = _color("Autenticado com Google:", "1;32")
            print(f"\n{ok} token ...{masked}")
            print(f"{_color('Provider google_auth pronto para uso via OAuth.', 90)}\n")
        except Exception as e:
            erro = _color("Erro na autenticacao Google:", "1;31")
            print(f"\n{erro} {e}\n", file=sys.stderr)
    elif subcmd in ("revoke", "logout", "clear"):
        revoke_credentials()
        print(f"\n{_color('🗑️  Credenciais Google revogadas.', 33)}\n")
    elif subcmd in ("status", "check"):
        if has_valid_credentials():
            print(f"\n{_color('✅ Credenciais Google OAuth ativas.', 32)}\n")
        else:
            print(f"\n{_color('⚠️  Credenciais Google OAuth não encontradas ou expiradas.', 33)}")
            print(f"{_color('Use:', 90)} /auth google\n")
    else:
        print(f"\n{_color('❌ Uso:', '1;31')} /auth google | /auth status | /auth revoke\n")
