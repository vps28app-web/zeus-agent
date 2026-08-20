"""Unit tests for context pruning and summarization."""

from zeus.memory.context import estimate_tokens, prune_messages, summarize_turns


def test_estimate_tokens():
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens({"key": "value"}) >= 1


def test_summarize_turns():
    turns = [
        {"role": "user", "content": "Como funciona o Zeus?"},
        {"role": "assistant", "content": "O Zeus é um harness de agente.", "tool_calls": []},
        {"role": "tool", "name": "read_file", "content": "content of file"},
    ]
    summary = summarize_turns(turns)
    assert "User asked" in summary
    assert "Assistant responded" in summary
    assert "read_file" in summary


def test_prune_messages_no_pruning_needed():
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    pruned = prune_messages(messages, max_messages=10, max_tokens=1000)
    assert len(pruned) == 3
    assert pruned == messages


def test_prune_messages_triggers_pruning():
    messages = [{"role": "system", "content": "System prompt"}]
    for i in range(15):
        messages.append({"role": "user", "content": f"User question {i}"})
        messages.append({"role": "assistant", "content": f"Assistant answer {i}"})

    pruned = prune_messages(messages, max_messages=10, keep_recent=4)

    # System prompt + Summary message + 4 recent messages = 6 total
    assert len(pruned) == 6
    assert pruned[0]["role"] == "system"
    assert "Earlier Conversation Summary" in pruned[1]["content"]
    assert pruned[-1]["content"] == "Assistant answer 14"


def test_prune_messages_truncates_long_tool_output():
    long_output = "x" * 10000
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Run"},
        {"role": "tool", "name": "terminal", "content": long_output},
    ]
    pruned = prune_messages(messages, max_messages=10, max_tokens=100000)
    tool_msg = pruned[-1]
    assert tool_msg["role"] == "tool"
    assert len(tool_msg["content"]) < len(long_output)
    assert "truncated" in tool_msg["content"]


def test_prune_messages_recursive_on_token_limit():
    messages = [{"role": "system", "content": "System prompt"}]
    for i in range(30):
        messages.append({"role": "user", "content": "User " + "word " * 50})
        messages.append({"role": "assistant", "content": "Assistant " + "word " * 50})

    pruned = prune_messages(messages, max_messages=100, max_tokens=700, keep_recent=2)
    total = sum(estimate_tokens(m.get("content", "")) for m in pruned)
    assert total <= 700
    assert pruned[0]["role"] == "system"
