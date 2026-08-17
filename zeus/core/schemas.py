"""Pydantic schemas for structured LLM outputs."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCallDecision(BaseModel):
    """A single tool call the model wants to make."""

    name: str = Field(..., description="Name of the tool to call.")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool.")


class AgentDecision(BaseModel):
    """Structured decision returned by the agent LLM."""

    reasoning: str = Field(
        ...,
        description="Brief internal reasoning about what to do next.",
    )
    response: Optional[str] = Field(
        None,
        description="Direct response to the user. Must be set when no tool_calls are provided.",
    )
    tool_calls: List[ToolCallDecision] = Field(
        default_factory=list,
        description="List of tool calls to execute. Empty if responding directly.",
    )


class PlanStep(BaseModel):
    """A single step in a generated plan."""

    step: int = Field(..., description="Step number.")
    action: str = Field(..., description="Short actionable description.")
    tool_hint: str = Field("any", description="Suggested tool or 'any'.")


class PlanOutput(BaseModel):
    """Structured plan output."""

    title: str = Field(..., description="Short plan title.")
    steps: List[PlanStep] = Field(..., description="Numbered list of plan steps.")


def decision_json_schema() -> Dict[str, Any]:
    """Return the JSON schema for AgentDecision."""
    return AgentDecision.model_json_schema()


def plan_json_schema() -> Dict[str, Any]:
    """Return the JSON schema for PlanOutput."""
    return PlanOutput.model_json_schema()
