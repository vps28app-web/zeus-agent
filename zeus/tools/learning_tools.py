"""Tools for continuous learning: capture and search past resolutions."""

from typing import Any, Dict, Optional

from zeus.core.registry import register_tool
from zeus.memory.learning import LearningStore


def reflect_on_resolution(
    problem: str,
    solution: str,
    tools_used: Optional[str] = None,
    tags: Optional[str] = None,
    failure_pattern: Optional[str] = None,
) -> Dict[str, Any]:
    """Save a problem/solution pattern learned after resolving an issue."""
    store = LearningStore()
    tools_list = [t.strip() for t in (tools_used or "").split(",") if t.strip()]
    tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    tags_list.extend(["manual", "resolution"])
    learning_id = store.save(
        problem=problem.strip(),
        solution=solution.strip(),
        tools_used=tools_list,
        tags=list(set(tags_list)),
        failure_pattern=failure_pattern,
        effectiveness_score=2,
    )
    return {
        "status": "success",
        "learning_id": learning_id,
        "message": "Aprendizado salvo. Será usado em tarefas futuras.",
    }


def search_past_learnings(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search past learnings relevant to a query or problem."""
    store = LearningStore()
    results = store.search(query, limit=limit)
    return {
        "query": query,
        "count": len(results),
        "learnings": results,
    }


def rate_learning(learning_id: int, helpful: bool) -> Dict[str, Any]:
    """Rate a learning as helpful or not, adjusting its future relevance."""
    store = LearningStore()
    store.rate(learning_id, helpful)
    return {
        "status": "success",
        "learning_id": learning_id,
        "helpful": helpful,
        "message": "Feedback registrado.",
    }


def list_recent_learnings(limit: int = 10) -> Dict[str, Any]:
    """List recently captured learnings."""
    store = LearningStore()
    return {
        "count": limit,
        "learnings": store.list_recent(limit=limit),
    }


register_tool(
    name="reflect_on_resolution",
    description="Salva um padrão de problema/solução aprendido para reutilização futura.",
    parameters={
        "type": "object",
        "properties": {
            "problem": {"type": "string", "description": "Descrição concisa do problema."},
            "solution": {"type": "string", "description": "Solução aplicada."},
            "tools_used": {"type": "string", "description": "Ferramentas usadas, separadas por vírgula."},
            "tags": {"type": "string", "description": "Tags separadas por vírgula."},
            "failure_pattern": {"type": "string", "description": "Erro ou padrão de falha observado."},
        },
        "required": ["problem", "solution"],
    },
    handler=reflect_on_resolution,
    tags=["memory", "learning"],
)

register_tool(
    name="search_past_learnings",
    description="Busca aprendizados passados relevantes para uma tarefa ou problema.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Tarefa ou problema para buscar aprendizados similares."},
            "limit": {"type": "integer", "description": "Máximo de resultados.", "default": 5},
        },
        "required": ["query"],
    },
    handler=search_past_learnings,
    tags=["memory", "learning", "read"],
)

register_tool(
    name="rate_learning",
    description="Avalia se um aprendizado foi útil (ajusta score de relevância).",
    parameters={
        "type": "object",
        "properties": {
            "learning_id": {"type": "integer", "description": "ID do aprendizado."},
            "helpful": {"type": "boolean", "description": "True se foi útil, False se não."},
        },
        "required": ["learning_id", "helpful"],
    },
    handler=rate_learning,
    tags=["memory", "learning"],
)

register_tool(
    name="list_recent_learnings",
    description="Lista os aprendizados mais recentes.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Máximo de resultados.", "default": 10},
        },
    },
    handler=list_recent_learnings,
    tags=["memory", "learning", "read"],
)
