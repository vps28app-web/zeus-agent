"""Context Management: Pruning & Summarization for long conversation sessions."""

import json
import os
from typing import Any, Dict, List, Optional


# Conservative character-per-token estimate for mixed text/code.
CHARS_PER_TOKEN = 3.5
MAX_TOOL_OUTPUT_CHARS = 4000
MAX_SUMMARY_CHARS = 1200


def estimate_tokens(content: Any) -> int:
    """Estimate token count for content."""
    if isinstance(content, str):
        return max(1, int(len(content) / CHARS_PER_TOKEN))
    if isinstance(content, (dict, list)):
        return max(1, int(len(json.dumps(content, ensure_ascii=False)) / CHARS_PER_TOKEN))
    return 1


def summarize_turns(turns: List[Dict[str, Any]]) -> str:
    """Generate a concise summary of older conversation turns."""
    summaries = []
    for turn in turns:
        role = turn.get("role", "unknown")
        content = turn.get("content", "")
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        content_str = str(content or "").strip()
        if len(content_str) > 150:
            content_str = content_str[:147] + "..."

        if role == "user":
            summaries.append(f"- User asked/requested: {content_str}")
        elif role == "assistant":
            if turn.get("tool_calls"):
                tools = [c.get("function", {}).get("name") for c in turn["tool_calls"]]
                summaries.append(f"- Assistant called tools ({', '.join(filter(None, tools))}): {content_str}")
            else:
                summaries.append(f"- Assistant responded: {content_str}")
        elif role == "tool":
            tool_name = turn.get("name", "tool")
            summaries.append(f"- Tool ({tool_name}) output recorded")

    summary = "\n".join(summaries)
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[:MAX_SUMMARY_CHARS] + "\n... [summary truncated]"
    return summary


def _truncate_tool_content(content: Any) -> Any:
    """Truncate very long tool outputs to avoid context explosion."""
    if not isinstance(content, str):
        return content
    if len(content) <= MAX_TOOL_OUTPUT_CHARS:
        return content
    half = MAX_TOOL_OUTPUT_CHARS // 2
    head = content[:half]
    tail = content[-half:]
    removed = len(content) - MAX_TOOL_OUTPUT_CHARS
    return f"{head}\n\n... [truncated {removed} chars] ...\n\n{tail}"


def _normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a copy with long tool outputs truncated."""
    normalized = []
    for m in messages:
        copy = dict(m)
        if copy.get("role") == "tool":
            copy["content"] = _truncate_tool_content(copy.get("content"))
        normalized.append(copy)
    return normalized


def prune_messages(
    messages: List[Dict[str, Any]],
    max_messages: Optional[int] = None,
    max_tokens: Optional[int] = None,
    keep_recent: int = 6,
) -> List[Dict[str, Any]]:
    """
    Prune and summarize message history if it exceeds max_messages or max_tokens limits.
    Preserves system prompt (messages[0]) and the most recent `keep_recent` messages.
    Recursively prunes if the resulting context is still too large.
    """
    if max_messages is None:
        max_messages = int(os.getenv("ZEUS_MAX_CONTEXT_MESSAGES", "14"))
    if max_tokens is None:
        max_tokens = int(os.getenv("ZEUS_MAX_CONTEXT_TOKENS", "8000"))

    messages = _normalize_messages(messages)

    # Keep system prompt if present.
    system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
    non_system = messages[1:] if system_msg else messages[:]

    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

    if len(non_system) <= max_messages and total_tokens <= max_tokens:
        return messages

    if len(non_system) <= keep_recent:
        return [system_msg] + non_system if system_msg else non_system

    old_turns = non_system[:-keep_recent]
    recent_turns = non_system[-keep_recent:]

    summary_text = summarize_turns(old_turns)
    summary_message = {
        "role": "system",
        "content": f"## Earlier Conversation Summary ({len(old_turns)} turns pruned)\n{summary_text}",
    }

    result = []
    if system_msg:
        result.append(system_msg)
    result.append(summary_message)
    result.extend(recent_turns)

    # Recurse if still over limits; grow keep_recent to avoid infinite loops.
    new_total = sum(estimate_tokens(m.get("content", "")) for m in result)
    if (len(result) > max_messages or new_total > max_tokens) and keep_recent < len(non_system):
        return prune_messages(result, max_messages, max_tokens, keep_recent + 2)

    return result
