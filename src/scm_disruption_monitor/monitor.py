from __future__ import annotations

import json
from pathlib import Path

from scm_disruption_monitor.laya_client import assess_offline, assess_with_laya, laya_api_key
from scm_disruption_monitor.models import DisruptionAssessment, DisruptionEvent


def load_events(path: Path) -> list[DisruptionEvent]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [DisruptionEvent.model_validate(item) for item in raw]


def assess_all(events: list[DisruptionEvent], *, live: bool) -> list[DisruptionAssessment]:
    use_live = live and bool(laya_api_key())
    if live and not use_live:
        raise RuntimeError("Live mode requires LAYA_API_KEY")
    assess = assess_with_laya if use_live else assess_offline
    return [assess(event) for event in events]
