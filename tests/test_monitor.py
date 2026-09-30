from pathlib import Path

from scm_disruption_monitor.monitor import assess_all, load_events


def test_load_and_assess_sample_offline() -> None:
    sample = Path(__file__).resolve().parents[1] / "data" / "sample_disruptions.json"
    events = load_events(sample)
    assert len(events) == 3
    results = assess_all(events, live=False)
    assert {r.event_id for r in results} == {"evt-001", "evt-002", "evt-003"}
    critical = next(r for r in results if r.event_id == "evt-003")
    assert critical.severity == "critical"
    assert critical.escalate is True
