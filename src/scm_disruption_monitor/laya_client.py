from __future__ import annotations

import os
from typing import Any

import httpx

from scm_disruption_monitor.models import DisruptionAssessment, DisruptionEvent

LAYA_DEFAULT_BASE = "https://api.laya.studio"


def laya_base_url() -> str:
    return os.environ.get("LAYA_BASE_URL", LAYA_DEFAULT_BASE).rstrip("/")


def laya_api_key() -> str | None:
    key = os.environ.get("LAYA_API_KEY")
    return key.strip() if key else None


def build_systemone_payload(event: DisruptionEvent) -> dict[str, Any]:
    state = {
        "supplier": event.supplier,
        "region": event.region,
        "summary": event.summary,
        "days_delayed": event.days_delayed,
        "affected_skus": event.affected_skus,
    }
    questions = {
        "severity": {
            "type": "choice",
            "instructions": "How severe is this supply-chain disruption?",
            "criteria": {
                "low": "minor delay, alternate suppliers available",
                "medium": "meaningful delay or partial SKU impact",
                "high": "major delay, critical SKUs at risk",
                "critical": "production stop or safety/regulatory risk",
            },
        },
        "escalate": {
            "type": "noul",
            "instructions": "Should operations leadership be escalated immediately?",
        },
    }
    return {"state": state, "questions": questions, "model": "english"}


def parse_systemone_response(event_id: str, body: dict[str, Any]) -> DisruptionAssessment:
    answers = body.get("answers") or {}
    severity_block = answers.get("severity") or {}
    escalate_block = answers.get("escalate") or {}
    severity = str(severity_block.get("choice") or "medium")
    noul = escalate_block.get("noul")
    escalate = bool(noul >= 0.5) if isinstance(noul, (int, float)) else severity in {
        "high",
        "critical",
    }
    conf = severity_block.get("confidence")
    rationale = f"Laya severity={severity}"
    if conf is not None:
        rationale += f" (confidence={conf})"
    return DisruptionAssessment(
        event_id=event_id,
        severity=severity,
        escalate=escalate,
        rationale=rationale,
        source="laya",
    )


def assess_with_laya(event: DisruptionEvent, *, timeout: float = 30.0) -> DisruptionAssessment:
    api_key = laya_api_key()
    if not api_key:
        raise RuntimeError("LAYA_API_KEY is not set")

    url = f"{laya_base_url()}/v1/systemone"
    payload = build_systemone_payload(event)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return parse_systemone_response(event.id, response.json())


def assess_offline(event: DisruptionEvent) -> DisruptionAssessment:
    """Deterministic fallback when no Laya credentials are configured."""
    if event.days_delayed >= 14 or len(event.affected_skus) >= 5:
        severity = "critical"
    elif event.days_delayed >= 7 or len(event.affected_skus) >= 2:
        severity = "high"
    elif event.days_delayed >= 3:
        severity = "medium"
    else:
        severity = "low"
    escalate = severity in {"high", "critical"}
    return DisruptionAssessment(
        event_id=event.id,
        severity=severity,
        escalate=escalate,
        rationale="Offline heuristic from delay days and SKU count",
        source="offline",
    )
