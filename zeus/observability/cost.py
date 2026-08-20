"""Simple cost estimation for LLM providers.

Prices are per 1M tokens in USD. These are approximate defaults;
users can override via ZEUS_COST_OVERRIDES or config.yaml.
"""

import json
import os
from typing import Any, Dict

DEFAULT_PRICES: Dict[str, Dict[str, float]] = {
    # Provider/model -> {input, output}
    "openrouter/auto": {"input": 0.0, "output": 0.0},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3-haiku": {"input": 0.25, "output": 1.25},
    "google/gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "google/gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "kimi-k2.7-code": {"input": 0.0, "output": 0.0},
    "ollama/llama3.1": {"input": 0.0, "output": 0.0},
}


def _load_overrides() -> Dict[str, Dict[str, float]]:
    raw = os.getenv("ZEUS_COST_OVERRIDES", "{}")
    try:
        overrides = json.loads(raw)
        if isinstance(overrides, dict):
            return overrides
    except json.JSONDecodeError:
        pass
    return {}


def _normalize_model(provider: str, model: str) -> str:
    if "/" in model:
        return model
    return f"{provider}/{model}"


def get_price(provider: str, model: str) -> Dict[str, float]:
    key = _normalize_model(provider, model)
    overrides = _load_overrides()
    if key in overrides:
        return overrides[key]
    if model in DEFAULT_PRICES:
        return DEFAULT_PRICES[model]
    if key in DEFAULT_PRICES:
        return DEFAULT_PRICES[key]
    return {"input": 0.0, "output": 0.0}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Dict[str, Any]:
    """Return estimated cost in USD for a given provider/model and token counts."""
    price = get_price(provider, model)
    input_cost = (input_tokens / 1_000_000) * price["input"]
    output_cost = (output_tokens / 1_000_000) * price["output"]
    return {
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_price_per_1m": price["input"],
        "output_price_per_1m": price["output"],
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(input_cost + output_cost, 6),
        "currency": "USD",
    }
