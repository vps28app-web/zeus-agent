"""Isolated Python code execution tool backed by the Go sandbox."""

import base64
import json
from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool
from zeus.security.permissions import PermissionManager, check_python_safety, check_shell_safety
from zeus.tools.sandbox_client import run_sandboxed_command, safe_environment

_permissions = PermissionManager()


def execute_python(
    code: str,
    inputs: Optional[Dict[str, Any]] = None,
    packages: Optional[List[str]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Execute Python code inside the Go sandbox.

    The code receives a `inputs` dict serialized to JSON and can print to stdout.
    """
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("execute_python", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for execute_python. Try again later."}

    if not _permissions.can_run_sandboxed_python():
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_execution(
            tool="execute_python", command=code[:500],
            result={"error": _permissions.denied_message("execute_python")},
            allowed=False,
        )
        return {"error": _permissions.denied_message("execute_python")}

    safety = check_python_safety(code, allow_install=_permissions.can_install_packages())
    if safety:
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_execution(
            tool="execute_python", command=code[:500],
            result={"error": safety},
            allowed=False,
        )
        return {"error": safety}

    # Build a wrapper script that deserializes inputs and runs user code.
    # Both inputs and user code are base64-encoded so the wrapper never contains
    # the raw user code, avoiding issues with triple quotes or shell metachars.
    import shlex

    inputs_json = json.dumps(inputs or {})
    encoded_inputs = base64.b64encode(inputs_json.encode("utf-8")).decode("utf-8")
    encoded_code = base64.b64encode(code.encode("utf-8")).decode("utf-8")

    wrapper = f'''import base64, json
_inputs_json = base64.b64decode("{encoded_inputs}").decode("utf-8")
_inputs = json.loads(_inputs_json)
_user_code_bytes = base64.b64decode("{encoded_code}")
_user_code = _user_code_bytes.decode("utf-8")
_globals = {{"inputs": _inputs}}
exec(_user_code, _globals)
'''

    # Encode the entire wrapper to base64 so we can pass it safely through shell
    encoded_wrapper = base64.b64encode(wrapper.encode("utf-8")).decode("utf-8")

    install_packages = ""
    if packages:
        if not _permissions.can_install_packages():
            return {"error": _permissions.denied_message("package installation")}
        # Validate package names to prevent shell injection, then quote each.
        import re

        for pkg in packages:
            if not re.fullmatch(r"[A-Za-z0-9_\-\.\[\]>=<~!]+", pkg):
                return {"error": f"Invalid package name: {pkg}"}
        install_packages = "pip install --quiet " + " ".join(shlex.quote(pkg) for pkg in packages) + " && "

    shell_command = (
        f"{install_packages}"
        f"python3 -c \"$(echo '{encoded_wrapper}' | base64 -d)\""
    )

    result = run_sandboxed_command(shell_command, timeout=timeout, env=safe_environment())
    from zeus.security.audit import get_audit_logger
    get_audit_logger().log_execution(tool="execute_python", command=code[:500], result=result)
    return result


def execute_shell_script(
    script: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Execute an arbitrary shell script inside the Go sandbox."""
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("execute_shell_script", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for execute_shell_script. Try again later."}

    if not _permissions.can_run_sandboxed_shell():
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_execution(
            tool="execute_shell_script", command=script[:500],
            result={"error": _permissions.denied_message("execute_shell_script")},
            allowed=False,
        )
        return {"error": _permissions.denied_message("execute_shell_script")}

    safety = check_shell_safety(script)
    if safety:
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_execution(
            tool="execute_shell_script", command=script[:500],
            result={"error": safety},
            allowed=False,
        )
        return {"error": safety}

    encoded_script = base64.b64encode(script.encode("utf-8")).decode("utf-8")
    shell_command = f"echo '{encoded_script}' | base64 -d | bash"
    result = run_sandboxed_command(shell_command, timeout=timeout, env=safe_environment())
    from zeus.security.audit import get_audit_logger
    get_audit_logger().log_execution(tool="execute_shell_script", command=script[:500], result=result)
    return result


register_tool(
    name="execute_python",
    description="Execute Python code inside the isolated sandbox. Use for calculations, data processing, and safe code experiments.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute."},
            "inputs": {"type": "object", "description": "Variables exposed as the 'inputs' dict inside the code."},
            "packages": {"type": "array", "items": {"type": "string"}, "description": "Python packages to install before running."},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["code"],
    },
    handler=execute_python,
    tags=["code", "execute"],
)

register_tool(
    name="execute_shell_script",
    description="Execute a shell script inside the isolated sandbox.",
    parameters={
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "Shell script content to execute."},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["script"],
    },
    handler=execute_shell_script,
    tags=["code", "execute"],
)
