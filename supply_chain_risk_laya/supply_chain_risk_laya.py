#!/usr/bin/env python3
"""
Manufacturing Control Tower triage using Laya typed decisions.

Runnable locally or from Google Colab after mounting Drive and cd'ing into the project folder.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union

import config

logger = logging.getLogger(__name__)

AlertInput = Union[str, Mapping[str, Any]]

# ---------------------------------------------------------------------------
# Laya question schema (verified against laya 0.3.x score = ordered criteria list)
# ---------------------------------------------------------------------------


def get_supply_chain_questions() -> dict[str, Any]:
    """Return the Control Tower Laya question set."""
    return {
        "is_supply_chain_relevant": {
            "type": "noul",
            "instructions": (
                "Does this news event describe a situation that could materially "
                "affect manufacturing supply, suppliers, raw materials, production, "
                "transportation, logistics, inventory or physical goods movement?"
            ),
        },
        "disruption_category": {
            "type": "choice",
            "instructions": (
                "Which segment of the supply chain does this event primarily disrupt?"
            ),
            "criteria": {
                "logistics_transport": (
                    "Strikes, port closures, shipping delays, transportation "
                    "accidents, customs disruption, freight disruption or blocked movement."
                ),
                "supplier_financial": (
                    "Supplier bankruptcy, insolvency, financial distress, acquisition "
                    "or other supplier financial problems."
                ),
                "environmental_hazard": (
                    "Weather events, floods, earthquakes, hurricanes, fires or "
                    "other natural/environmental events affecting supply chain facilities."
                ),
                "labor_shortage": (
                    "Factory worker shortages, manufacturing labor disputes or "
                    "production workforce disruption."
                ),
            },
        },
        "severity_index": {
            "type": "score",
            "instructions": (
                "Rate the operational severity of the supply chain disruption from 0 to 3."
            ),
            "criteria": [
                "0 = minor or negligible operational impact",
                "1 = low impact; manageable delay with limited operational consequence",
                "2 = significant disruption; production, inventory or transportation may be affected",
                "3 = critical disruption; physical goods or critical raw materials are blocked",
            ],
        },
        "trigger_backup_sourcing": {
            "type": "noul",
            "instructions": (
                "Does this event create an immediate need to activate an "
                "alternative supplier, alternative sourcing route, or emergency "
                "procurement process because the movement or availability of "
                "physical goods is materially disrupted?"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Input validation and business rules (no Laya dependency)
# ---------------------------------------------------------------------------


class AlertValidationError(ValueError):
    """Raised when alert input cannot be processed."""


def normalize_alert_input(alert_text_or_state: AlertInput) -> dict[str, str]:
    """Accept plain text or a dict with alert_text; return normalized state fields."""
    if isinstance(alert_text_or_state, str):
        text = alert_text_or_state.strip()
        if not text:
            raise AlertValidationError("Alert text is empty.")
        return {"source_type": "Unspecified Alert", "alert_text": text}

    if not isinstance(alert_text_or_state, Mapping):
        raise AlertValidationError(
            f"Expected str or mapping for alert input, got {type(alert_text_or_state)!r}."
        )

    alert_text = str(alert_text_or_state.get("alert_text", "")).strip()
    if not alert_text:
        raise AlertValidationError("Missing or empty 'alert_text' in alert state.")
    source_type = str(alert_text_or_state.get("source_type", "Unspecified Alert"))
    return {"source_type": source_type, "alert_text": alert_text}


def build_laya_state(normalized: Mapping[str, str]) -> dict[str, str]:
    """State object passed to Router.predict (Control Tower event envelope)."""
    return {
        "source_type": normalized["source_type"],
        "alert_text": normalized["alert_text"],
    }


def _noul_probability(answer: Mapping[str, Any]) -> Optional[float]:
    value = answer.get("noul")
    if isinstance(value, (int, float)):
        return float(value)
    logger.error("Missing or invalid noul probability in Laya answer: %s", answer)
    return None


def _choice_answer(answer: Mapping[str, Any]) -> tuple[Optional[str], dict[str, float]]:
    choice = answer.get("choice")
    raw_probs = answer.get("probabilities") or {}
    probabilities: dict[str, float] = {}
    if isinstance(raw_probs, Mapping):
        for key, val in raw_probs.items():
            if isinstance(val, (int, float)):
                probabilities[str(key)] = float(val)
    if choice is None:
        logger.error("Missing choice in Laya answer: %s", answer)
        return None, probabilities
    return str(choice), probabilities


def _score_answer(answer: Mapping[str, Any]) -> tuple[Optional[int], Optional[float], dict[str, float]]:
    score_raw = answer.get("score")
    raw_probs = answer.get("probabilities") or {}
    probabilities: dict[str, float] = {}
    if isinstance(raw_probs, Mapping):
        for key, val in raw_probs.items():
            if isinstance(val, (int, float)):
                probabilities[str(key)] = float(val)
    if not isinstance(score_raw, (int, float)):
        logger.error("Missing or invalid score in Laya answer: %s", answer)
        return None, None, probabilities
    score_float = float(score_raw)
    score_int = int(round(score_float))
    score_int = max(0, min(3, score_int))
    return score_int, score_float, probabilities


def compute_priority(
    severity: Optional[int],
    backup_probability: Optional[float],
    *,
    supply_chain_relevant: bool,
    backup_threshold: float = config.BACKUP_SOURCING_THRESHOLD,
) -> str:
    """
    Deterministic demo Control Tower priority (not an ML prediction).

    Returns NOT_RELEVANT when the article fails the relevance gate upstream.
    """
    if not supply_chain_relevant:
        return "NOT_RELEVANT"
    if severity is None or backup_probability is None:
        return "UNKNOWN"

    if severity == 3 and backup_probability >= backup_threshold:
        return "CRITICAL"
    if severity >= 2 or backup_probability >= backup_threshold:
        return "HIGH"
    if severity == 1:
        return "MEDIUM"
    if severity == 0:
        return "LOW"
    return "UNKNOWN"


def parse_laya_result(
    normalized_alert: Mapping[str, str],
    laya_payload: Mapping[str, Any],
    *,
    backup_threshold: float = config.BACKUP_SOURCING_THRESHOLD,
    relevance_threshold: float = config.RELEVANCE_THRESHOLD,
) -> dict[str, Any]:
    """Map raw Laya system_one payload to Control Tower JSON."""
    answers = laya_payload.get("answers")
    if not isinstance(answers, Mapping):
        raise ValueError("Malformed Laya result: missing 'answers' object.")

    routing = laya_payload.get("routing") or {}
    model_name = routing.get("model") if isinstance(routing, Mapping) else None

    relevance_answer = answers.get("is_supply_chain_relevant")
    if not isinstance(relevance_answer, Mapping):
        raise ValueError("Malformed Laya result: missing is_supply_chain_relevant answer.")
    relevance_probability = _noul_probability(relevance_answer)
    supply_chain_relevant = (
        relevance_probability is not None and relevance_probability >= relevance_threshold
    )

    category_answer = answers.get("disruption_category")
    severity_answer = answers.get("severity_index")
    backup_answer = answers.get("trigger_backup_sourcing")
    if not all(isinstance(a, Mapping) for a in (category_answer, severity_answer, backup_answer)):
        raise ValueError("Malformed Laya result: missing required typed answers.")

    category, category_probabilities = _choice_answer(category_answer)
    category_probability = None
    if category and category in category_probabilities:
        category_probability = category_probabilities[category]

    severity_index, severity_score_raw, severity_probabilities = _score_answer(severity_answer)
    backup_probability = _noul_probability(backup_answer)

    trigger_backup = False
    if supply_chain_relevant and backup_probability is not None:
        trigger_backup = backup_probability >= backup_threshold

    priority = compute_priority(
        severity_index,
        backup_probability,
        supply_chain_relevant=supply_chain_relevant,
        backup_threshold=backup_threshold,
    )

    return {
        "source_type": normalized_alert["source_type"],
        "alert_text": normalized_alert["alert_text"],
        "supply_chain_relevant": supply_chain_relevant,
        "relevance_probability": relevance_probability,
        "disruption_category": {
            "choice": category,
            "probabilities": category_probabilities,
            "probability": category_probability,
        },
        "severity_index": {
            "score": severity_index,
            "score_raw": severity_score_raw,
            "probabilities": severity_probabilities,
        },
        "trigger_backup_sourcing": {
            "probability": backup_probability,
            "trigger": trigger_backup,
        },
        "priority": priority,
        "laya_model": model_name,
        "raw_laya_response": dict(laya_payload),
    }


def export_for_business_central(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """
    Prepare normalized JSON payload for future Business Central integration.

    No API call is made in this prototype.
    """
    payload: list[dict[str, Any]] = []
    for row in results:
        payload.append(
            {
                "externalReference": row.get("article_id") or row.get("id"),
                "sourceType": row.get("source_type"),
                "alertText": row.get("alert_text"),
                "supplyChainRelevant": row.get("supply_chain_relevant"),
                "relevanceProbability": row.get("relevance_probability"),
                "disruptionCategory": row.get("disruption_category"),
                "severityIndex": row.get("severity_index"),
                "backupSourcingProbability": row.get("backup_sourcing_probability")
                or (row.get("trigger_backup_sourcing") or {}).get("probability"),
                "triggerBackupSourcing": row.get("trigger_backup_sourcing"),
                "controlTowerPriority": row.get("priority"),
                "layaModel": row.get("laya_model"),
            }
        )
    return payload


# ---------------------------------------------------------------------------
# Laya runtime
# ---------------------------------------------------------------------------


def detect_compute_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        logger.debug("torch not available for device detection")
    return "cpu"


def create_router(preload: Optional[bool] = None):
    """Initialize a shared Laya Router instance."""
    try:
        from laya import Router
    except ImportError as exc:
        raise RuntimeError(
            "Failed to import laya. Install requirements.txt (pip install -r requirements.txt)."
        ) from exc

    use_preload = config.USE_PRELOAD if preload is None else preload
    device = detect_compute_device()
    logger.info("Initializing Laya Router (preload=%s, detected_device=%s)", use_preload, device)
    try:
        return Router(preload=use_preload, device=device)
    except TypeError:
        return Router(preload=use_preload)


def analyze_supply_chain_risk(
    alert_text_or_state: AlertInput,
    router=None,
    *,
    backup_threshold: float = config.BACKUP_SOURCING_THRESHOLD,
    relevance_threshold: float = config.RELEVANCE_THRESHOLD,
) -> dict[str, Any]:
    """
    Run Laya typed inference and return normalized Control Tower JSON.

    Initializes Router lazily when router is None (avoid for batch — pass a shared instance).
    """
    normalized = normalize_alert_input(alert_text_or_state)
    state = build_laya_state(normalized)
    questions = get_supply_chain_questions()

    if router is None:
        router = create_router()

    try:
        raw = router.predict(state, questions)
    except Exception as exc:
        raise RuntimeError(f"Laya inference failed: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise ValueError("Unexpected Laya response type (expected mapping).")

    return parse_laya_result(
        normalized,
        raw,
        backup_threshold=backup_threshold,
        relevance_threshold=relevance_threshold,
    )


# ---------------------------------------------------------------------------
# AG News
# ---------------------------------------------------------------------------


def load_ag_news_dataset():
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "datasets package is required for AG News batch mode. pip install datasets"
        ) from exc

    logger.info("Loading Hugging Face dataset fancyzhx/ag_news (train split)...")
    try:
        return load_dataset("fancyzhx/ag_news", split="train")
    except Exception as exc:
        raise RuntimeError(f"Failed to load AG News dataset: {exc}") from exc


def inspect_ag_news_dataset(dataset) -> None:
    label_names = config.AG_NEWS_LABEL_NAMES
    labels = list(dataset["label"])
    distribution: dict[str, int] = {name: 0 for name in label_names.values()}
    for label_id in labels:
        name = label_names.get(int(label_id), str(label_id))
        distribution[name] = distribution.get(name, 0) + 1

    print(f"AG News records   : {len(dataset)}")
    print(f"Columns           : {dataset.column_names}")
    print(f"Label names       : {label_names}")
    print(f"Label distribution: {distribution}")


def process_ag_news(
    dataset,
    router,
    limit: int = config.AG_NEWS_SAMPLE_SIZE,
    business_world_only: bool = True,
) -> "Any":
    import pandas as pd

    questions = get_supply_chain_questions()
    rows: list[dict[str, Any]] = []
    processed = 0

    for idx, record in enumerate(dataset):
        if processed >= limit:
            break
        label_id = int(record["label"])
        if business_world_only and label_id not in config.AG_NEWS_FOCUS_LABELS:
            continue

        alert_text = str(record["text"])
        normalized = {
            "source_type": "AG News Feed",
            "alert_text": alert_text,
        }
        state = build_laya_state(normalized)
        raw = router.predict(state, questions)
        parsed = parse_laya_result(normalized, raw)

        rows.append(
            {
                "article_id": idx,
                "ag_news_label": config.AG_NEWS_LABEL_NAMES.get(label_id, str(label_id)),
                "source_type": parsed["source_type"],
                "alert_text": parsed["alert_text"],
                "supply_chain_relevant": parsed["supply_chain_relevant"],
                "relevance_probability": parsed["relevance_probability"],
                "disruption_category": parsed["disruption_category"]["choice"],
                "disruption_category_probability": parsed["disruption_category"].get(
                    "probability"
                ),
                "severity_index": parsed["severity_index"]["score"],
                "backup_sourcing_probability": parsed["trigger_backup_sourcing"]["probability"],
                "trigger_backup_sourcing": parsed["trigger_backup_sourcing"]["trigger"],
                "priority": parsed["priority"],
                "laya_model": parsed["laya_model"],
            }
        )
        processed += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reporting, persistence, visualization
# ---------------------------------------------------------------------------


def flatten_for_csv(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_type": result.get("source_type"),
        "alert_text": result.get("alert_text"),
        "supply_chain_relevant": result.get("supply_chain_relevant"),
        "relevance_probability": result.get("relevance_probability"),
        "disruption_category": (result.get("disruption_category") or {}).get("choice"),
        "disruption_category_probability": (result.get("disruption_category") or {}).get(
            "probability"
        ),
        "severity_index": (result.get("severity_index") or {}).get("score"),
        "backup_sourcing_probability": (result.get("trigger_backup_sourcing") or {}).get(
            "probability"
        ),
        "trigger_backup_sourcing": (result.get("trigger_backup_sourcing") or {}).get("trigger"),
        "priority": result.get("priority"),
        "laya_model": result.get("laya_model"),
    }


def print_control_tower_report(result: Mapping[str, Any]) -> None:
    rel_yes = "YES" if result.get("supply_chain_relevant") else "NO"
    rel_prob = result.get("relevance_probability")
    category = (result.get("disruption_category") or {}).get("choice")
    cat_prob = (result.get("disruption_category") or {}).get("probability")
    severity = (result.get("severity_index") or {}).get("score")
    backup_prob = (result.get("trigger_backup_sourcing") or {}).get("probability")
    backup_trigger = (result.get("trigger_backup_sourcing") or {}).get("trigger")
    trigger_label = "TRIGGER" if backup_trigger else "HOLD"
    if result.get("priority") == "NOT_RELEVANT":
        trigger_label = "HOLD"

    print("=" * 57)
    print("SUPPLY CHAIN CONTROL TOWER - LAYA TRIAGE")
    print("=" * 57)
    print()
    print("Alert:")
    print(result.get("alert_text", ""))
    print()
    print(f"Supply Chain Relevant : {rel_yes}")
    print(f"Relevance Probability : {rel_prob}")
    print()
    print(f"Disruption Category   : {category}")
    print(f"Category Probability  : {cat_prob}")
    print()
    print(f"Severity Index        : {severity} / 3")
    print()
    print(f"Backup Sourcing Prob. : {backup_prob}")
    print(f"Backup Sourcing       : {trigger_label}")
    print()
    print(f"Control Tower Priority: {result.get('priority')}")
    print()
    print(f"Laya Model            : {result.get('laya_model')}")
    print("=" * 57)
    print()
    print("Raw Laya response (debug):")
    print(json.dumps(result.get("raw_laya_response"), indent=2, default=str))


def save_results(
    results: Sequence[Mapping[str, Any]],
    *,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    import pandas as pd

    out_dir = Path(output_dir or config.OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "control_tower_results.json"
    csv_path = out_dir / "control_tower_results.csv"

    serializable = [dict(r) for r in results]
    json_path.write_text(json.dumps(serializable, indent=2, default=str), encoding="utf-8")

    flat_rows = [flatten_for_csv(r) for r in results]
    pd.DataFrame(flat_rows).to_csv(csv_path, index=False)
    logger.info("Wrote %s and %s", json_path, csv_path)
    return json_path, csv_path


def plot_risk_summary(df) -> None:
    """Optional matplotlib summary charts."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    category_counts = df["disruption_category"].fillna("unknown").value_counts()
    axes[0].bar(category_counts.index.astype(str), category_counts.values)
    axes[0].set_title("Alerts by disruption category")
    axes[0].tick_params(axis="x", rotation=45)

    severity_counts = df["severity_index"].fillna(-1).astype(int).value_counts().sort_index()
    axes[1].bar(severity_counts.index.astype(str), severity_counts.values)
    axes[1].set_title("Severity distribution")

    trigger_counts = df["trigger_backup_sourcing"].fillna(False).value_counts()
    axes[2].bar([str(k) for k in trigger_counts.index], trigger_counts.values)
    axes[2].set_title("Backup sourcing triggers")

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Demo entrypoints
# ---------------------------------------------------------------------------


def load_sample_alerts(path: Optional[Path] = None) -> list[dict[str, Any]]:
    sample_path = path or (config.PROJECT_ROOT / "sample_alerts.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("sample_alerts.json must contain a JSON list.")
    return data


def run_demo_port_strike(router) -> dict[str, Any]:
    state = {
        "source_type": "Macro News Alert",
        "alert_text": (
            "Unionized transport workers at the key regional port have initiated "
            "a wildcat strike, halting all inbound container unloading of steel "
            "and aluminum for the next 48 hours."
        ),
    }
    return analyze_supply_chain_risk(state, router=router)


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supply Chain Control Tower Laya triage")
    parser.add_argument(
        "--ag-news",
        action="store_true",
        help="Run optional AG News batch sample after the primary demo.",
    )
    parser.add_argument(
        "--sample-library",
        action="store_true",
        help="Process all records in sample_alerts.json.",
    )
    parser.add_argument(
        "--no-preload",
        action="store_true",
        help="Use Router(preload=False) to reduce memory (slower first inference).",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Show matplotlib summary when batch results exist.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_logging()
    args = parse_args(argv)

    try:
        import laya as laya_pkg
    except ImportError:
        logger.error("laya is not installed. Run: pip install -r requirements.txt")
        return 1

    laya_version = getattr(laya_pkg, "__version__", "unknown")
    device = detect_compute_device()
    print(f"Laya version: {laya_version}")
    print(f"Compute device: {device}")

    init_start = time.perf_counter()
    router = create_router(preload=False if args.no_preload else None)
    init_seconds = time.perf_counter() - init_start
    print(f"Initialization time : {init_seconds:.2f} sec")

    infer_start = time.perf_counter()
    demo_result = run_demo_port_strike(router)
    infer_seconds = time.perf_counter() - infer_start
    print(f"Inference time      : {infer_seconds:.3f} sec")
    print()

    print_control_tower_report(demo_result)
    all_results: list[dict[str, Any]] = [demo_result]

    run_library = args.sample_library or config.RUN_SAMPLE_LIBRARY
    if run_library:
        for alert in load_sample_alerts():
            enriched = dict(alert)
            parsed = analyze_supply_chain_risk(alert, router=router)
            parsed["id"] = alert.get("id")
            all_results.append(parsed)

    run_ag_news = args.ag_news or config.RUN_AG_NEWS_BATCH
    batch_seconds: Optional[float] = None
    if run_ag_news:
        dataset = load_ag_news_dataset()
        inspect_ag_news_dataset(dataset)
        batch_start = time.perf_counter()
        df = process_ag_news(dataset, router, limit=config.AG_NEWS_SAMPLE_SIZE)
        batch_seconds = time.perf_counter() - batch_start
        if len(df):
            avg = batch_seconds / len(df)
            print(f"AG News batch time  : {batch_seconds:.2f} sec ({len(df)} rows, avg {avg:.3f} sec)")
        for record in df.to_dict(orient="records"):
            all_results.append(record)
        if args.plot or config.ENABLE_PLOT:
            plot_risk_summary(df)

    save_results(all_results)
    bc_payload = export_for_business_central(all_results)
    logger.info("Prepared %d Business Central-ready records (no API call).", len(bc_payload))

    return 0


if __name__ == "__main__":
    sys.exit(main())
