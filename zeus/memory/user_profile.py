"""User profile learning: extract and persist names, preferences, and habits."""

import json
import os
import re
from typing import Any, Dict, List, Optional

from zeus.db.connection import init_db
from zeus.db.repository import UserProfileRepository


_NAME_PATTERNS = [
    re.compile(r"meu nome (?:é|e|eh)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE),
    re.compile(r"(?:pode me chamar de|me chame de)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE),
    re.compile(r"sou (?:o|a)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE),
]

_PREFERENCE_PATTERNS = [
    re.compile(r"(?:eu )?(?:gosto de|prefiro|adoro)\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE),
    re.compile(r"(?:não gosto de|odeio|evito)\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE),
]

_HABIT_PATTERNS = [
    re.compile(r"(?:sempre|costumo|toda|todos)\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE),
    re.compile(r"(?:minha rotina|meu costume)\s+(?:é|e|eh)\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE),
]


def _extract_by_patterns(text: str, patterns: List[re.Pattern]) -> List[str]:
    results: List[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group(1).strip()
            if len(value) > 2 and value not in results:
                results.append(value)
    return results


def extract_profile_signals(text: str) -> Dict[str, Any]:
    """Extract potential profile signals from a single message using heuristics."""
    names = _extract_by_patterns(text, _NAME_PATTERNS)
    preferences = _extract_by_patterns(text, _PREFERENCE_PATTERNS)
    habits = _extract_by_patterns(text, _HABIT_PATTERNS)
    return {
        "name": names[0] if names else None,
        "preferences": preferences,
        "habits": habits,
    }


def extract_profile_signals_with_llm(text: str) -> Dict[str, Any]:
    """Extract profile signals using a lightweight LLM call as fallback/enrichment."""
    import os

    from zeus.core.router import chat

    prompt = f"""Analise a mensagem abaixo e extraia informações sobre o usuário.
Retorne APENAS um objeto JSON com este formato exacto:
{{"name": "..." ou null, "preferences": ["..."], "habits": ["..."]}}

Mensagem: \"{text}\"
"""
    messages = [
        {"role": "system", "content": "Você é um extrator de perfil de usuário. Responda apenas com JSON válido."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = chat(messages, tools=[], provider=os.getenv("ZEUS_PROFILE_PROVIDER"), model=os.getenv("ZEUS_PROFILE_MODEL"))
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Strip markdown fences if present.
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
            content = content.removeprefix("json").strip()
        parsed = json.loads(content)
        return {
            "name": parsed.get("name") or None,
            "preferences": [p for p in parsed.get("preferences", []) if isinstance(p, str)],
            "habits": [h for h in parsed.get("habits", []) if isinstance(h, str)],
        }
    except Exception:
        return {"name": None, "preferences": [], "habits": []}


class UserProfileStore:
    """High-level store for user profiles with automatic signal extraction."""

    def __init__(self, repo: Optional[UserProfileRepository] = None):
        init_db()
        self._repo = repo or UserProfileRepository()

    def _extract(self, text: str) -> Dict[str, Any]:
        """Combine heuristic extraction with optional LLM enrichment."""
        heuristic = extract_profile_signals(text)
        if any([heuristic["name"], heuristic["preferences"], heuristic["habits"]]):
            return heuristic

        if os.getenv("ZEUS_PROFILE_USE_LLM", "false").lower() in ("1", "true", "yes"):
            return extract_profile_signals_with_llm(text)

        return heuristic

    def learn_from_message(
        self,
        user_id: str,
        platform: Optional[str],
        text: str,
        role: str = "user",
    ) -> Dict[str, Any]:
        """Extract signals from a message and update the user's profile."""
        if role != "user":
            return {"updated": False, "reason": "only user messages are learned"}

        signals = self._extract(text)
        if not any([signals["name"], signals["preferences"], signals["habits"]]):
            return {"updated": False, "reason": "no signals found"}

        self._repo.upsert(
            user_id=user_id,
            platform=platform,
            name=signals["name"],
            preferences=signals["preferences"],
            habits=signals["habits"],
            raw_notes=text.strip(),
        )
        return {"updated": True, "signals": signals}

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._repo.get(user_id)

    def format_context(self, user_id: str) -> str:
        """Return a concise profile snippet to inject into the system prompt."""
        profile = self.get_profile(user_id)
        if not profile:
            return ""

        lines = []
        if profile.get("name"):
            lines.append(f"Nome do usuário: {profile['name']}.")
        if profile.get("preferences"):
            lines.append("Preferências: " + "; ".join(profile["preferences"]) + ".")
        if profile.get("habits"):
            lines.append("Costumes: " + "; ".join(profile["habits"]) + ".")
        return " ".join(lines)

    def list_profiles(self) -> List[Dict[str, Any]]:
        return self._repo.list_all()

    def forget_user(self, user_id: str) -> None:
        self._repo.delete(user_id)
