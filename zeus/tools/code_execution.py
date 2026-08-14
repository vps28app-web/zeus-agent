"""Isolated Python code execution tool backed by the Go sandbox."""

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool
from zeus.tools.sandbox_client import run_sandboxed_command


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
    # Build a wrapper script that deserializes inputs and runs user code
    inputs_json = json.dumps(inputs or {})
    encoded_inputs = base64.b64encode(inputs_json.encode("utf-8")).decode("utf-8")

    wrapper = f'''import base64, json, sys
_inputs = json.loads(base64.b64decode("{encoded_inputs}").decode("utf-8"))
_globals = {{"inputs": _inputs}}
_user_code = """
{code}
"""
exec(_user_code, _globals)
'''

    # Encode the entire wrapper to base64 so we can pass it safely through shell
    encoded_wrapper = base64.b64encode(wrapper.encode("utf-8")).decode("utf-8")

    install_packages = ""
    if packages:
        install_packages = "pip install --quiet " + " ".join(packages) + " && "

    shell_command = (
        f"{install_packages}"
        f"python3 -c \"$(echo '{encoded_wrapper}' | base64 -d)\""
    )

    return run_sandboxed_command(shell_command, timeout=timeout)


def execute_shell_script(
    script: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Execute an arbitrary shell script inside the Go sandbox."""
    encoded_script = base64.b64encode(script.encode("utf-8")).decode("utf-8")
    shell_command = f"echo '{encoded_script}' | base64 -d | bash"
    return run_sandboxed_command(shell_command, timeout=timeout)


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
)
