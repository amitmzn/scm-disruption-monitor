from __future__ import annotations

from pydantic import BaseModel, Field


class DisruptionEvent(BaseModel):
    id: str
    supplier: str
    region: str
    summary: str
    days_delayed: int = Field(ge=0)
    affected_skus: list[str] = Field(default_factory=list)


class DisruptionAssessment(BaseModel):
    event_id: str
    severity: str
    escalate: bool
    rationale: str
    source: str
