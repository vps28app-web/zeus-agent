"""Context Management: Pruning & Summarization for long conversation sessions."""

import os
from typing import Any, Dict, List, Optional


def estimate_tokens(content: Any) -> int:
    """Estimate token count for content (approx 4 characters per token)."""
    if isinstance(content, str):
        return max(1, len(content) // 4)
    if isinstance(content, (dict, list)):
        import json
        return max(1, len(json.dumps(content)) // 4)
    return 1


def summarize_turns(turns: List[Dict[str, Any]]) -> str:
    """Generate a concise summary of older conversation turns."""
    summaries = []
    for turn in turns:
        role = turn.get("role", "unknown")
        content = turn.get("content", "")
        if isinstance(content, dict):
            import json
            content = json.dumps(content)
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
    
    return "\n".join(summaries)


def prune_messages(
    messages: List[Dict[str, Any]],
    max_messages: Optional[int] = None,
    max_tokens: Optional[int] = None,
    keep_recent: int = 6,
) -> List[Dict[str, Any]]:
    """
    Prune and summarize message history if it exceeds max_messages or max_tokens limits.
    Preserves system prompt (messages[0]) and the most recent `keep_recent` messages.
    """
    if max_messages is None:
        max_messages = int(os.getenv("ZEUS_MAX_CONTEXT_MESSAGES", "14"))
    if max_tokens is None:
        max_tokens = int(os.getenv("ZEUS_MAX_CONTEXT_TOKENS", "8000"))

    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    
    if len(messages) <= max_messages and total_tokens <= max_tokens:
        return messages

    # Keep system prompt if present
    system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
    non_system = messages[1:] if system_msg else messages[:]

    if len(non_system) <= keep_recent:
        return messages

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

    return result
