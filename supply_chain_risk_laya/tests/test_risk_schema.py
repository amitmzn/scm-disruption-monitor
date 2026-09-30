"""Unit tests for Control Tower business logic (no Laya model download)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import supply_chain_risk_laya as scr  # noqa: E402


def _sample_laya_payload(
    *,
    relevance: float = 0.95,
    category: str = "logistics_transport",
    category_prob: float = 0.91,
    severity_score: float = 2.8,
    backup_prob: float = 0.88,
) -> dict:
    return {
        "answers": {
            "is_supply_chain_relevant": {"type": "noul", "noul": relevance},
            "disruption_category": {
                "type": "choice",
                "choice": category,
                "probabilities": {category: category_prob, "labor_shortage": 0.09},
            },
            "severity_index": {
                "type": "score",
                "score": severity_score,
                "probabilities": {"0": 0.01, "1": 0.05, "2": 0.14, "3": 0.8},
            },
            "trigger_backup_sourcing": {"type": "noul", "noul": backup_prob},
        },
        "routing": {"model": "english", "reason": "test"},
    }


def test_normalize_alert_text_input() -> None:
    normalized = scr.normalize_alert_input("  Port closure reported.  ")
    assert normalized["alert_text"] == "Port closure reported."
    assert normalized["source_type"] == "Unspecified Alert"


def test_normalize_alert_dict_input() -> None:
    normalized = scr.normalize_alert_input(
        {"source_type": "Macro News Alert", "alert_text": "Strike at port."}
    )
    assert normalized["source_type"] == "Macro News Alert"


def test_missing_alert_text_raises() -> None:
    with pytest.raises(scr.AlertValidationError):
        scr.normalize_alert_input({"source_type": "x"})


def test_empty_alert_raises() -> None:
    with pytest.raises(scr.AlertValidationError):
        scr.normalize_alert_input("   ")


def test_parse_laya_result_extracts_probabilities() -> None:
    normalized = {"source_type": "Macro News Alert", "alert_text": "Strike."}
    parsed = scr.parse_laya_result(normalized, _sample_laya_payload())
    assert parsed["disruption_category"]["choice"] == "logistics_transport"
    assert parsed["disruption_category"]["probability"] == pytest.approx(0.91)
    assert parsed["severity_index"]["score"] == 3
    assert parsed["trigger_backup_sourcing"]["probability"] == pytest.approx(0.88)
    assert parsed["trigger_backup_sourcing"]["trigger"] is True


def test_noul_threshold_backup_sourcing() -> None:
    normalized = {"source_type": "Alert", "alert_text": "Event"}
    low = scr.parse_laya_result(
        normalized,
        _sample_laya_payload(backup_prob=0.55, severity_score=1.0),
        backup_threshold=0.70,
    )
    assert low["trigger_backup_sourcing"]["trigger"] is False

    high = scr.parse_laya_result(
        normalized,
        _sample_laya_payload(backup_prob=0.75, severity_score=1.0),
        backup_threshold=0.70,
    )
    assert high["trigger_backup_sourcing"]["trigger"] is True


def test_priority_rules() -> None:
    assert scr.compute_priority(3, 0.80, supply_chain_relevant=True) == "CRITICAL"
    assert scr.compute_priority(2, 0.10, supply_chain_relevant=True) == "HIGH"
    assert scr.compute_priority(1, 0.10, supply_chain_relevant=True) == "MEDIUM"
    assert scr.compute_priority(0, 0.10, supply_chain_relevant=True) == "LOW"


def test_irrelevant_article_priority() -> None:
    normalized = {"source_type": "News", "alert_text": "Retail earnings beat estimates."}
    parsed = scr.parse_laya_result(
        normalized,
        _sample_laya_payload(relevance=0.20, backup_prob=0.99, severity_score=3.0),
        relevance_threshold=0.60,
    )
    assert parsed["supply_chain_relevant"] is False
    assert parsed["priority"] == "NOT_RELEVANT"
    assert parsed["trigger_backup_sourcing"]["trigger"] is False


def test_malformed_laya_result_raises() -> None:
    normalized = {"source_type": "Alert", "alert_text": "x"}
    with pytest.raises(ValueError):
        scr.parse_laya_result(normalized, {"answers": {}})


def test_export_for_business_central_shape() -> None:
    normalized = {"source_type": "Alert", "alert_text": "Strike"}
    parsed = scr.parse_laya_result(normalized, _sample_laya_payload())
    payload = scr.export_for_business_central([parsed])
    assert payload[0]["disruptionCategory"]["choice"] == "logistics_transport"
    assert payload[0]["controlTowerPriority"] == "CRITICAL"


def test_sample_alerts_file_has_ten_records() -> None:
    alerts = scr.load_sample_alerts()
    assert len(alerts) == 10
    assert alerts[0]["id"] == "SC001"


@pytest.mark.integration
def test_live_laya_port_strike_if_available() -> None:
    """Optional live test; skip when laya/torch cannot run inference."""
    pytest.importorskip("laya")
    router = scr.create_router(preload=False)
    result = scr.run_demo_port_strike(router)
    assert result["disruption_category"]["choice"] is not None
    assert result["raw_laya_response"]
