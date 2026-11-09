"""Request/response schemas for AI order insights (D9)."""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class InsightIn(BaseModel):
    """`POST /insights/question` — the ONLY client input.

    There is deliberately no target-customer field (AI-02): the analysis is
    always scoped to the authenticated user. The hard 1000-char schema cap
    bounds any request; the *configured* limit
    (``ai_max_question_chars``) is enforced by the service (422
    QUESTION_TOO_LONG) so it can be tuned without a code change.
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)


class InsightOut(BaseModel):
    """`answer` is None when the provider is unconfigured (the client then
    shows the configuration notice plus the exact app-computed `stats`).
    `provider` is never a secret: "openai:<model>" | "deterministic" |
    "unconfigured"."""

    model_config = ConfigDict(extra="forbid")

    answer: Optional[str] = None
    provider: str
    stats: dict[str, Any]
