"""Guardrails engine for input sanitization, pre-execution verification, scope limits, and output sanitization."""

import re
from pathlib import Path
from typing import Any, Dict, Optional

# Secrets patterns for automatic redaction
SECRET_PATTERNS = [
    re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,}[-_a-zA-Z0-9]*)\b"),  # OpenAI / generic API keys
    re.compile(r"\b(?:Bearer\s+[a-zA-Z0-9\-\._~\+\/]+=*)\b", re.IGNORECASE),  # Bearer tokens
    re.compile(r"\b(?:ghp_[a-zA-Z0-9]{36})\b"),  # GitHub personal access tokens
    re.compile(r"\b(?:AKIA[0-9A-Z]{16})\b"),  # AWS Access Key ID
]

# Sensitive paths blocked from direct tool operations
PROTECTED_PATHS = [
    re.compile(r"^/etc/(?:passwd|shadow|sudoers)"),
    re.compile(r"^/root(?:/.*)?$"),
    re.compile(r".*\.ssh(?:/.*)?$"),
    re.compile(r".*\.env(?:\..*)?$"),
]

# Prompt injection attempt patterns
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?prior\s+prompts", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+DAN\s+mode", re.IGNORECASE),
    re.compile(r"system\s+override\s+code", re.IGNORECASE),
    re.compile(r"bypass\s+security\s+filter", re.IGNORECASE),
]


class GuardrailViolation(Exception):
    """Raised when a guardrail rule blocks execution."""

    def __init__(self, stage: str, rule: str, message: str):
        self.stage = stage  # 'input', 'tool', 'output'
        self.rule = rule
        self.message = message
        super().__init__(message)


class GuardrailsManager:
    """Centralized guardrail engine enforcing pre-model, pre-tool, and post-model security rules."""

    def __init__(
        self,
        enable_prompt_injection_check: bool = True,
        enable_secret_redaction: bool = True,
        enable_path_protection: bool = True,
        max_input_length: int = 32000,
    ):
        self.enable_prompt_injection_check = enable_prompt_injection_check
        self.enable_secret_redaction = enable_secret_redaction
        self.enable_path_protection = enable_path_protection
        self.max_input_length = max_input_length

    # ------------------------------------------------------------------
    # 1. Pre-Model (Input Guardrail)
    # ------------------------------------------------------------------
    def validate_input(self, user_input: str) -> str:
        """
        Validate and sanitize input before sending to the model.
        Returns sanitized input or raises GuardrailViolation.
        """
        if not user_input:
            return user_input

        if len(user_input) > self.max_input_length:
            raise GuardrailViolation(
                stage="input",
                rule="max_length_exceeded",
                message=f"Input length ({len(user_input)}) exceeds maximum allowed ({self.max_input_length}).",
            )

        if self.enable_prompt_injection_check:
            for pattern in PROMPT_INJECTION_PATTERNS:
                if pattern.search(user_input):
                    raise GuardrailViolation(
                        stage="input",
                        rule="prompt_injection_detected",
                        message="Input blocked due to potential prompt injection pattern.",
                    )

        if self.enable_secret_redaction:
            user_input = self.redact_secrets(user_input)

        return user_input

    # ------------------------------------------------------------------
    # 2. Pre-Tool Call (Tool Execution Guardrail)
    # ------------------------------------------------------------------
    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Validate tool calls before execution.
        Returns None if valid, or a dict with error if blocked by guardrails.
        """
        # Protected path check for file operations
        if self.enable_path_protection and tool_name in ("read_file", "write_file", "delete_file", "list_directory"):
            path = arguments.get("path", "")
            if path:
                try:
                    resolved = str(Path(path).expanduser().resolve())
                    for pattern in PROTECTED_PATHS:
                        if pattern.search(resolved):
                            return {
                                "error": f"Guardrail Blocked: Path '{path}' is a protected system path and cannot be accessed."
                            }
                except Exception:
                    pass

        # Terminal / Shell safety check.
        # run_terminal / run_background_command are NOT hard-blocked here:
        # in terminal mode they require explicit user confirmation (handled by
        # PermissionManager), and in auto mode the terminal tool itself blocks.
        # execute_shell_script (sandbox) has no human confirmation, so keep the
        # hard block for it.
        if tool_name == "execute_shell_script":
            cmd = arguments.get("command") or arguments.get("script") or ""
            from zeus.security.permissions import check_shell_safety
            safety_err = check_shell_safety(cmd)
            if safety_err:
                return {"error": f"Guardrail Blocked: {safety_err}"}

        # Python execution safety check
        if tool_name in ("execute_python", "run_sandboxed"):
            code = arguments.get("code") or arguments.get("script") or ""
            from zeus.security.permissions import check_python_safety
            safety_err = check_python_safety(code)
            if safety_err:
                return {"error": f"Guardrail Blocked: {safety_err}"}

        return None

    # ------------------------------------------------------------------
    # 3. Post-Model (Output Guardrail)
    # ------------------------------------------------------------------
    def sanitize_output(self, output: str) -> str:
        """Sanitize model output before returning to user (e.g. mask secrets/sensitive data)."""
        if not output:
            return output

        if self.enable_secret_redaction:
            output = self.redact_secrets(output)

        return output

    def redact_secrets(self, text: str) -> str:
        """Redact sensitive patterns (API keys, tokens) from text."""
        redacted = text
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED_SECRET]", redacted)
        return redacted
