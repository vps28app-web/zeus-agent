"""User profile learning: extract and persist names, preferences, and habits."""

import json
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
    """Extract potential profile signals from a single message."""
    names = _extract_by_patterns(text, _NAME_PATTERNS)
    preferences = _extract_by_patterns(text, _PREFERENCE_PATTERNS)
    habits = _extract_by_patterns(text, _HABIT_PATTERNS)
    return {
        "name": names[0] if names else None,
        "preferences": preferences,
        "habits": habits,
    }


class UserProfileStore:
    """High-level store for user profiles with automatic signal extraction."""

    def __init__(self, repo: Optional[UserProfileRepository] = None):
        init_db()
        self._repo = repo or UserProfileRepository()

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

        signals = extract_profile_signals(text)
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
