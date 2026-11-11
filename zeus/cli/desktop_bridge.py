"""Structured JSON Lines bridge for Zeus Desktop (Rust native UI)."""

import contextlib
import io
import json
import os
import re
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from zeus.cli.commands import (
    _handle_auth_command,
    _handle_config_command,
    _handle_learning_command,
    _handle_mcp_command,
    _handle_mode_command,
    _load_env,
    _print_brain_dashboard,
    _print_command_menu,
    _print_skills_menu,
)
from zeus.cli.setup_commands import MODEL_PRESETS, PROVIDER_ENV_VARS
from zeus.core.agent import run_agent, run_summary
from zeus.core.planner import execute_plan_step, generate_bmad_plan, generate_plan
from zeus.core.registry import REGISTRY
from zeus.core.team import create_default_team
from zeus.memory.session_log import get_logger
from zeus.observability import get_metrics
from zeus.observability.cost import estimate_cost

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

PROVIDER_NAMES = {
    "opencode_go": "OpenCode Go",
    "google_api": "Google Gemini",
    "google_auth": "Google Gemini (OAuth)",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "anthropic": "Anthropic Claude",
    "deepseek": "DeepSeek",
    "mistral": "Mistral AI",
    "ollama": "Ollama (Local)",
    "groq": "Groq",
    "xai": "xAI (Grok)",
    "together": "Together AI",
    "fireworks": "Fireworks AI",
    "cohere": "Cohere",
}

DESKTOP_COMMANDS: List[Dict[str, str]] = [
    {"cmd": "/new", "desc": "Cria uma nova sessão de conversa com novo ID.", "category": "Sessão & Sistema"},
    {"cmd": "/reset", "desc": "Reseta a sessão atual mantendo o ID e zera métricas.", "category": "Sessão & Sistema"},
    {"cmd": "/clear", "desc": "Limpa as mensagens visíveis da tela.", "category": "Sessão & Sistema"},
    {"cmd": "/summary", "desc": "Mostra resumo da sessão e consumo de tokens/custo.", "category": "Sessão & Sistema"},
    {"cmd": "/help", "desc": "Exibe menu de ajuda com a lista de comandos do Zeus.", "category": "Sessão & Sistema"},
    {"cmd": "/config", "desc": "Gerencia configurações do Zeus (get/set/list).", "category": "Configuração & IA"},
    {"cmd": "/models", "desc": "Lista provedores e modelos de IA configurados.", "category": "Configuração & IA"},
    {"cmd": "/auth", "desc": "Autentica Google Gemini via navegador (google_auth).", "category": "Configuração & IA"},
    {"cmd": "/skills", "desc": "Lista ou seleciona skill set/persona para filtrar ferramentas.", "category": "Configuração & IA"},
    {"cmd": "/mode <sandbox|terminal|auto|dryrun|readonly>", "desc": "Alterna modo de execução de código e segurança.", "category": "Segurança & Modos"},
    {"cmd": "/mode file <read_only|project_only|unrestricted>", "desc": "Define fronteira de permissão de escrita/leitura em disco.", "category": "Segurança & Modos"},
    {"cmd": "/mode status", "desc": "Exibe modo atual e status de segurança do agente.", "category": "Segurança & Modos"},
    {"cmd": "/plan <tarefa>", "desc": "Cria e executa um plano estruturado passo a passo.", "category": "Planejamento & Equipe"},
    {"cmd": "/plan bmad <ideia>", "desc": "Análise BMAD de modelo de negócio para uma ideia.", "category": "Planejamento & Equipe"},
    {"cmd": "/team <tarefa>", "desc": "Executa uma tarefa delegando para equipe multi-agente.", "category": "Planejamento & Equipe"},
    {"cmd": "/learn", "desc": "Gerencia aprendizados persistentes (list/search/add/stats/forget).", "category": "Memória & Aprendizado"},
    {"cmd": "/brain", "desc": "Dashboard de inteligência e aprendizado contínuo.", "category": "Memória & Aprendizado"},
    {"cmd": "/mcp", "desc": "Gerencia servidores Model Context Protocol (list/add/remove/reload).", "category": "Protocolo MCP"},
]


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _categorize_tool(tags: List[str]) -> str:
    tag_set = {t.lower() for t in tags}
    if tag_set & {"file", "filesystem", "files", "search", "code_intel"}:
        return "Arquivos & Diretórios"
    if tag_set & {"terminal", "sandbox", "execution", "packages", "ssh"}:
        return "Terminal & Execução"
    if tag_set & {"git"}:
        return "Git & Versionamento"
    if tag_set & {"web", "browser"}:
        return "Web & Navegação"
    if tag_set & {"memory", "profile", "user_profile"}:
        return "Memória & Perfil"
    if tag_set & {"learning"}:
        return "Aprendizado Contínuo"
    if tag_set & {"scheduler"}:
        return "Agendador (Scheduler)"
    if tag_set & {"config", "database"}:
        return "Configuração & Sistema"
    if tag_set & {"mcp"}:
        return "MCP (Servidores Externos)"
    return "Outras Ferramentas"


def build_desktop_catalog() -> Dict[str, Any]:
    """Build full dynamic catalog (providers, tools, commands, MCP, ecosystem) for Zeus Desktop."""
    _load_env(override=False)

    providers = []
    for pid, models in MODEL_PRESETS.items():
        providers.append(
            {
                "id": pid,
                "name": PROVIDER_NAMES.get(pid, pid),
                "models": [{"id": mid, "label": mlabel} for mid, mlabel in models],
                "env_vars": list(PROVIDER_ENV_VARS.get(pid, ())),
            }
        )

    tools = []
    for tool in REGISTRY.list_tools():
        tools.append(
            {
                "name": tool.name,
                "desc": tool.description,
                "category": _categorize_tool(tool.tags),
                "tags": list(tool.tags),
            }
        )

    mcp_servers: Dict[str, Any] = {}
    mcp_config_path = ""
    try:
        from zeus.mcp.config import MCPConfig

        cfg = MCPConfig()
        mcp_config_path = str(cfg.config_path)
        mcp_servers = {name: srv.to_dict() for name, srv in cfg.servers.items()}
    except Exception:
        pass

    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    env_file = zeus_home / ".env"

    all_env_keys = sorted({k for keys in PROVIDER_ENV_VARS.values() for k in keys})
    configured_keys = {k: bool(os.getenv(k)) for k in all_env_keys}

    memories: List[Dict[str, Any]] = []
    scheduled_tasks: List[Dict[str, Any]] = []
    recent_sessions: List[Dict[str, Any]] = []
    try:
        from zeus.db.connection import get_connection
        from zeus.db.repository import MemoryRepository, ScheduledTaskRepository

        mem_repo = MemoryRepository()
        for key in mem_repo.keys()[:50]:
            memories.append({"key": key, "notes": mem_repo.get(key)})

        sched_repo = ScheduledTaskRepository()
        scheduled_tasks = sched_repo.list_all()

        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT s.session_id,
                       COALESCE(SUM(m.llm_input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(m.llm_output_tokens), 0) AS output_tokens,
                       COUNT(m.id) AS records,
                       s.created_at
                FROM sessions s
                LEFT JOIN metrics m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.rowid DESC
                LIMIT 20
                """
            ).fetchall()
            recent_sessions = [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        pass

    return {
        "providers": providers,
        "commands": DESKTOP_COMMANDS,
        "tools": tools,
        "mcp": {
            "config_path": mcp_config_path,
            "servers": mcp_servers,
        },
        "env": {
            "env_file": str(env_file),
            "provider": os.getenv("ZEUS_PROVIDER", ""),
            "model": os.getenv("ZEUS_MODEL", ""),
            "configured_keys": configured_keys,
        },
        "ecosystem": {
            "memories": memories,
            "scheduled_tasks": scheduled_tasks,
            "recent_sessions": recent_sessions,
        },
    }


class _JsonlEmitter:
    """Thread-safe JSON Lines emitter writing strictly to the raw stdout pipe."""

    def __init__(self, stream):
        self._stream = stream
        self._lock = threading.Lock()
        self._stdin_lock = threading.Lock()

    def emit(self, event_type: str, **payload: Any) -> None:
        obj = {"type": event_type, **payload}
        line = json.dumps(obj, ensure_ascii=False, default=str)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def request_permission(
        self,
        kind: str,
        message: str,
        options: Optional[List[str]] = None,
        secret: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        req_id = str(uuid.uuid4())
        self.emit(
            "permission_request",
            id=req_id,
            kind=kind,
            message=_strip_ansi(message),
            options=options or ["once", "deny"],
            secret=secret,
            details=details or {},
        )
        with self._stdin_lock:
            while True:
                raw_line = sys.stdin.readline()
                if not raw_line:
                    return {"decision": "deny"}
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    resp = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if resp.get("id") in (None, req_id):
                    return resp


class _StdoutRedirector(io.TextIOBase):
    """Redirect accidental plain prints into structured tool_output events."""

    def __init__(self, emitter: _JsonlEmitter):
        super().__init__()
        self._emitter = emitter
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            cleaned = _strip_ansi(line)
            if cleaned:
                self._emitter.emit("tool_output", chunk=cleaned)
        return len(s)

    def flush(self) -> None:
        if self._buf:
            cleaned = _strip_ansi(self._buf)
            self._buf = ""
            if cleaned:
                self._emitter.emit("tool_output", chunk=cleaned)


class _TurnStreamFilter:
    """Stream natural-language turns live while holding back raw JSON structured turns."""

    def __init__(self, emitter: _JsonlEmitter):
        self._emitter = emitter
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._buffer = ""
            self._mode = "detecting"  # detecting | streaming | suppressed_json
            self.streamed_any = False
            self.streamed_text = []

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        with self._lock:
            if self._mode == "suppressed_json":
                return
            if self._mode == "streaming":
                self.streamed_any = True
                self.streamed_text.append(chunk)
                self._emitter.emit("stream_chunk", content=chunk)
                return

            self._buffer += chunk
            stripped = self._buffer.lstrip()
            if not stripped:
                return
            if stripped.startswith("{") or stripped.startswith("```json"):
                self._mode = "suppressed_json"
                self._emitter.emit("status", text="Processando raciocínio...")
                return

            # Wait until at least 8 non-empty chars or a newline before committing to live stream
            # if it could still turn into ```json
            if len(stripped) < 7 and "```json".startswith(stripped):
                return

            self._mode = "streaming"
            flushed = self._buffer
            self._buffer = ""
            self.streamed_any = True
            self.streamed_text.append(flushed)
            self._emitter.emit("stream_chunk", content=flushed)

    def flush_pending(self) -> None:
        with self._lock:
            if self._mode == "detecting" and self._buffer:
                stripped = self._buffer.lstrip()
                if not (stripped.startswith("{") or stripped.startswith("```json")):
                    self._mode = "streaming"
                    flushed = self._buffer
                    self._buffer = ""
                    self.streamed_any = True
                    self.streamed_text.append(flushed)
                    self._emitter.emit("stream_chunk", content=flushed)


def _capture_command_output(fn: Callable[[], Any]) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return _strip_ansi(buf.getvalue()).strip()


def _format_plan_markdown(plan: Dict[str, Any]) -> str:
    lines = [f"### 📋 Plano: {plan.get('goal', 'Execução')}"]
    for step in plan.get("steps", []):
        num = step.get("step", "?")
        action = step.get("action", "")
        tool = step.get("tool")
        tool_hint = f" (`{tool}`)" if tool else ""
        lines.append(f"{num}. {action}{tool_hint}")
    return "\n".join(lines)


def _handle_desktop_slash_command(
    text: str,
    logger: Any,
    emitter: _JsonlEmitter,
) -> Optional[bool]:
    """Handle slash commands in desktop bridge mode. Returns True/False if handled, None if normal query."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    if stripped in ("/", "/help", "/?"):
        out = _capture_command_output(_print_command_menu)
        emitter.emit("final_response", content=out or "Menu de comandos exibido.")
        return True

    if stripped == "/summary":
        emitter.emit("final_response", content=_strip_ansi(run_summary(session_id=logger.session_id)))
        return True

    if stripped == "/brain":
        out = _capture_command_output(_print_brain_dashboard)
        emitter.emit("final_response", content=out)
        return True

    if stripped == "/learn" or stripped.startswith("/learn "):
        out = _capture_command_output(lambda: _handle_learning_command(stripped))
        emitter.emit("final_response", content=out or "Comando /learn executado.")
        return True

    if stripped == "/mcp" or stripped.startswith("/mcp "):
        out = _capture_command_output(lambda: _handle_mcp_command(stripped))
        emitter.emit("final_response", content=out or "Comando /mcp executado.")
        emitter.emit("catalog_refresh")
        return True

    if stripped == "/config" or stripped.startswith("/config "):
        out = _capture_command_output(lambda: _handle_config_command(stripped))
        emitter.emit("final_response", content=out or "Configuração atualizada.")
        return True

    if stripped == "/mode" or stripped.startswith("/mode "):
        out = _capture_command_output(lambda: _handle_mode_command(stripped))
        emitter.emit("final_response", content=out or "Modo atualizado.")
        emitter.emit(
            "mode_changed",
            permission=os.getenv("ZEUS_EXECUTION_PERMISSION", "sandbox_only"),
            execution_mode=os.getenv("ZEUS_EXECUTION_MODE", "terminal"),
            dry_run=os.getenv("ZEUS_DRY_RUN", "0"),
            read_only=os.getenv("ZEUS_READ_ONLY", "0"),
        )
        return True

    if stripped == "/auth" or stripped.startswith("/auth "):
        out = _capture_command_output(lambda: _handle_auth_command(stripped))
        emitter.emit("final_response", content=out or "Comando /auth concluído.")
        return True

    if stripped == "/skills" or stripped.startswith("/skills "):
        from zeus.cli.main import SKILL_SETS

        if stripped == "/skills":
            out = _capture_command_output(lambda: _print_skills_menu(None))
            emitter.emit("final_response", content=out)
            return True
        skill_name = stripped[len("/skills "):].strip()
        if skill_name not in SKILL_SETS:
            emitter.emit(
                "final_response",
                content=f"Skill set desconhecido: `{skill_name}`. Opções: coding, security, research, memory, all.",
            )
            return False
        cfg = SKILL_SETS[skill_name]
        count = len(REGISTRY.schemas(tag_allowlist=cfg["tags"]))
        emitter.emit(
            "final_response",
            content=f"Skill set **{cfg['label']}** possui **{count}** ferramentas disponíveis.",
        )
        return True

    if stripped == "/new":
        new_logger = get_logger(new_session=True)
        emitter.emit("session_created", session_id=new_logger.session_id)
        emitter.emit("final_response", content=f"Nova sessão criada: `{new_logger.session_id}`")
        return True

    if stripped == "/reset":
        get_logger(logger.session_id)
        emitter.emit("final_response", content=f"Sessão `{logger.session_id}` resetada.")
        return True

    if stripped == "/models" or stripped == "/provider":
        lines = ["### 🌐 Provedores e Modelos Configurados", f"- Provedor ativo: `{os.getenv('ZEUS_PROVIDER', '')}`", f"- Modelo ativo: `{os.getenv('ZEUS_MODEL', '')}`", "", "Use o seletor na barra inferior ou **Configurações** para trocar."]
        emitter.emit("final_response", content="\n".join(lines))
        return True

    if stripped.startswith("/team "):
        task = stripped[len("/team "):].strip()
        if not task:
            emitter.emit("final_response", content="Uso: `/team <tarefa>`")
            return False
        logger.log_turn("user", stripped)
        emitter.emit("status", text="Executando equipe multi-agente...")
        team = create_default_team(session_id=logger.session_id)
        resp = team.run(task)
        logger.log_turn("assistant", resp)
        emitter.emit("final_response", content=str(resp))
        return True

    if stripped.startswith("/plan "):
        task = stripped[len("/plan "):].strip()
        if not task:
            emitter.emit("final_response", content="Uso: `/plan <tarefa>`")
            return False
        logger.log_turn("user", stripped)
        emitter.emit("status", text="Gerando plano...")
        if task.lower().startswith("bmad "):
            plan = generate_bmad_plan(task[len("bmad "):].strip())
        else:
            plan = generate_plan(task)
        plan_md = _format_plan_markdown(plan)
        emitter.emit("stream_chunk", content=plan_md + "\n\n")
        resp = emitter.request_permission(
            kind="plan_confirm",
            message="Executar este plano passo a passo?",
            options=["once", "deny"],
            details={"goal": plan.get("goal", ""), "steps": len(plan.get("steps", []))},
        )
        if resp.get("decision") not in ("once", "always", "persist"):
            emitter.emit("final_response", content=plan_md + "\n\n⏹ Plano cancelado pelo usuário.")
            return True

        results = []
        steps = plan.get("steps", [])
        for step in steps:
            emitter.emit("status", text=f"Executando passo {step.get('step', '?')}/{len(steps)}...")
            res = execute_plan_step(
                step,
                original_request=task,
                previous_results=results,
                session_id=logger.session_id,
            )
            results.append(res)
            step_line = f"**Passo {res['step']}**: {res['action']}\n{res['result']}"
            emitter.emit("stream_chunk", content=step_line + "\n\n")
        summary = "\n\n".join(f"Passo {r['step']}: {r['action']}\n{r['result']}" for r in results)
        logger.log_turn("assistant", summary)
        emitter.emit("final_response", content=plan_md + "\n\n" + summary)
        return True

    return None


def _safe_result_summary(result: Any) -> str:
    if isinstance(result, str):
        return result[:1200]
    try:
        return json.dumps(result, ensure_ascii=False, default=str)[:1200]
    except Exception:
        return str(result)[:1200]


def run_desktop_bridge(
    query: Optional[str] = None,
    session_id: Optional[str] = None,
    use_team: bool = False,
) -> int:
    """Run a single desktop interaction using JSONL over stdout/stdin."""
    _load_env(override=False)
    os.environ["ZEUS_LOCAL_CLI"] = "1"

    import zeus.cli.renderer as renderer_mod

    renderer_mod._COLOR_ENABLED = False

    raw_stdout = sys.stdout
    emitter = _JsonlEmitter(raw_stdout)
    stdout_proxy = _StdoutRedirector(emitter)

    if not query:
        line = sys.stdin.readline()
        query = line.strip()

    if not query:
        emitter.emit("error", message="Nenhuma instrução fornecida ao bridge desktop.")
        emitter.emit("done", success=False)
        return 1

    # Wire interactive permission callbacks to JSONL stdin/stdout
    from zeus.security.permissions import PermissionManager, set_global_permission_manager
    from zeus.tools.file import set_file_permission_callback
    from zeus.tools.terminal import set_stream_callback

    def _file_perm_cb(msg: str) -> str:
        resp = emitter.request_permission(
            kind="file_permission",
            message=msg,
            options=["once", "always", "persist", "deny"],
        )
        decision = str(resp.get("decision", "deny")).lower()
        return decision if decision in ("once", "always", "persist") else "deny"

    def _term_confirm_cb(msg: str) -> bool:
        resp = emitter.request_permission(
            kind="terminal_confirm",
            message=msg,
            options=["once", "deny"],
        )
        return str(resp.get("decision", "deny")).lower() in ("once", "always", "persist", "yes", "allow")

    def _sudo_password_cb(msg: str) -> Optional[str]:
        resp = emitter.request_permission(
            kind="sudo_password",
            message=msg,
            options=["once", "deny"],
            secret=True,
        )
        if str(resp.get("decision", "deny")).lower() == "deny":
            return None
        secret = resp.get("secret")
        return str(secret) if secret else None

    def _terminal_stream_cb(chunk: str, stream_name: str = "stdout") -> None:
        cleaned = _strip_ansi(chunk)
        if cleaned:
            emitter.emit("tool_output", chunk=cleaned, stream=stream_name)

    set_file_permission_callback(_file_perm_cb)
    set_stream_callback(_terminal_stream_cb)
    set_global_permission_manager(
        PermissionManager(
            confirm_callback=_term_confirm_cb,
            password_callback=_sudo_password_cb,
            exec_level=os.getenv("ZEUS_EXECUTION_PERMISSION", "sandbox_only"),
        )
    )

    # Start configured MCP servers cleanly
    try:
        from zeus.mcp.manager import MCPManager

        MCPManager.get_instance().start_all()
    except Exception:
        pass

    logger = get_logger(session_id)
    metrics = get_metrics(logger.session_id)
    success = True

    sys.stdout = stdout_proxy
    try:
        slash_handled = _handle_desktop_slash_command(query, logger, emitter)
        if slash_handled is not None:
            success = slash_handled
        else:
            logger.log_turn("user", query)
            stream_filter = _TurnStreamFilter(emitter)

            def _on_tool_start(fn_name: str, fn_args: Any) -> None:
                stream_filter.reset()
                args_str = fn_args if isinstance(fn_args, str) else json.dumps(fn_args, ensure_ascii=False, default=str)
                emitter.emit("tool_start", name=fn_name, arguments=args_str)
                emitter.emit("status", text=f"Executando {fn_name}...")

            def _on_tool_result(fn_name: str, fn_args: Any, result: Any) -> None:
                err = None
                if isinstance(result, dict):
                    err = result.get("error")
                    if not err and isinstance(result.get("result"), dict):
                        err = result["result"].get("error")
                emitter.emit(
                    "tool_result",
                    name=fn_name,
                    result=_safe_result_summary(result),
                    error=str(err) if err else None,
                )
                stream_filter.reset()

            if use_team:
                emitter.emit("status", text="Executando equipe multi-agente...")
                team = create_default_team(session_id=logger.session_id)
                response = team.run(query)
            else:
                response = run_agent(
                    query,
                    session_id=logger.session_id,
                    stream=True,
                    stream_callback=stream_filter.feed,
                    tool_callback=_on_tool_start,
                    tool_result_callback=_on_tool_result,
                )

            # Interactive escalation loops (sudo / SSH / file permissions)
            while isinstance(response, dict) and (
                response.get("permission_required")
                or response.get("sudo_required")
                or response.get("ssh_user_required")
                or response.get("ssh_password_required")
            ):
                if response.get("permission_required"):
                    perm = response["permission_required"]
                    action = perm.get("action", "escrita")
                    path_str = perm.get("path", "")
                    choice = _file_perm_cb(f"Operação: {action}\nArquivo: {path_str}")
                    if choice in ("once", "always", "persist"):
                        from zeus.tools.file import get_file_permission_manager

                        get_file_permission_manager().grant_permission(action, Path(path_str), scope=choice)
                        stream_filter.reset()
                        response = run_agent(
                            response.get("pending_input", query),
                            session_id=logger.session_id,
                            stream=True,
                            stream_callback=stream_filter.feed,
                            tool_callback=_on_tool_start,
                            tool_result_callback=_on_tool_result,
                        )
                    else:
                        response = f"Permissão negada pelo usuário para '{action}' em '{path_str}'."
                        break
                elif response.get("sudo_required"):
                    sudo_info = response["sudo_required"]
                    pw = _sudo_password_cb(
                        f"Sudo necessário para: {sudo_info.get('command', 'operação administrativa')}"
                    )
                    if pw:
                        stream_filter.reset()
                        response = run_agent(
                            response.get("pending_input", query),
                            session_id=logger.session_id,
                            stream=True,
                            stream_callback=stream_filter.feed,
                            tool_callback=_on_tool_start,
                            tool_result_callback=_on_tool_result,
                        )
                    else:
                        response = "Operação sudo cancelada pelo usuário."
                        break
                elif response.get("ssh_user_required"):
                    ssh_req = response["ssh_user_required"]
                    resp = emitter.request_permission(
                        kind="ssh_user",
                        message=f"Usuário SSH para {ssh_req.get('host', '')}:{ssh_req.get('port', 22)}",
                        options=["once", "deny"],
                        secret=False,
                    )
                    ssh_user = (resp.get("secret") or "").strip()
                    if ssh_user and resp.get("decision") != "deny":
                        from zeus.tools.ssh_run import ssh_run

                        ssh_res = ssh_run(
                            host=ssh_req.get("host", ""),
                            command=ssh_req.get("command", ""),
                            user=ssh_user,
                            port=ssh_req.get("port", 22),
                        )
                        response = f"SSH result: {json.dumps(ssh_res, ensure_ascii=False, default=str)}"
                    else:
                        response = "Operação SSH cancelada pelo usuário."
                        break
                elif response.get("ssh_password_required"):
                    ssh_req = response["ssh_password_required"]
                    resp = emitter.request_permission(
                        kind="ssh_password",
                        message=f"Senha SSH para {ssh_req.get('user', '')}@{ssh_req.get('host', '')}",
                        options=["once", "deny"],
                        secret=True,
                    )
                    pw = resp.get("secret") or ""
                    if pw and resp.get("decision") != "deny":
                        from zeus.tools.ssh_run import ssh_run

                        ssh_res = ssh_run(
                            host=ssh_req.get("host", ""),
                            command=ssh_req.get("command", ""),
                            user=ssh_req.get("user", ""),
                            port=ssh_req.get("port", 22),
                            password=pw,
                        )
                        response = f"SSH result: {json.dumps(ssh_res, ensure_ascii=False, default=str)}"
                    else:
                        response = "Operação SSH cancelada pelo usuário."
                        break

            stream_filter.flush_pending()
            resp_text = str(response)
            logger.log_turn("assistant", resp_text)

            if isinstance(response, str) and response.startswith("LLM error:"):
                success = False
                emitter.emit("error", message=resp_text)
            elif not stream_filter.streamed_any or "".join(stream_filter.streamed_text).strip() != resp_text.strip():
                emitter.emit("final_response", content=resp_text, replace=stream_filter.streamed_any)
    except Exception as exc:
        success = False
        logger.log_turn("error", str(exc))
        emitter.emit("error", message=str(exc))
    finally:
        stdout_proxy.flush()
        sys.stdout = raw_stdout

    snap = metrics.snapshot()
    provider = os.getenv("ZEUS_PROVIDER", "openrouter")
    model = os.getenv("ZEUS_MODEL", "openrouter/auto")
    cost_info = estimate_cost(
        provider,
        model,
        snap.get("llm_input_tokens", 0),
        snap.get("llm_output_tokens", 0),
    )
    emitter.emit(
        "metrics",
        session_id=logger.session_id,
        llm_calls=snap.get("llm_calls", 0),
        input_tokens=snap.get("llm_input_tokens", 0),
        output_tokens=snap.get("llm_output_tokens", 0),
        latency_ms=snap.get("llm_total_latency_ms", 0.0),
        total_cost_usd=cost_info.get("total_cost_usd", 0.0),
    )
    emitter.emit("done", success=success)
    return 0 if success else 1
