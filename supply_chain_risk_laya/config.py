"""Configuration for the Supply Chain Control Tower Laya prototype."""

from __future__ import annotations

import os
from pathlib import Path

# Resolve project root: env override for Colab/Drive, else directory containing this file.
PROJECT_ROOT = Path(
    os.environ.get("SCM_PROJECT_ROOT", Path(__file__).resolve().parent)
).resolve()

AG_NEWS_SAMPLE_SIZE = int(os.environ.get("AG_NEWS_SAMPLE_SIZE", "20"))
BACKUP_SOURCING_THRESHOLD = float(os.environ.get("BACKUP_SOURCING_THRESHOLD", "0.70"))
RELEVANCE_THRESHOLD = float(os.environ.get("RELEVANCE_THRESHOLD", "0.60"))
USE_PRELOAD = os.environ.get("USE_PRELOAD", "true").lower() in {"1", "true", "yes"}
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "output"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# AG News label id -> name (fancyzhx/ag_news)
AG_NEWS_LABEL_NAMES: dict[int, str] = {
    0: "World",
    1: "Sports",
    2: "Business",
    3: "Sci/Tech",
}

# Labels to include when business_world_only=True (World + Business)
AG_NEWS_FOCUS_LABELS: frozenset[int] = frozenset({0, 2})

RUN_AG_NEWS_BATCH = os.environ.get("RUN_AG_NEWS_BATCH", "false").lower() in {"1", "true", "yes"}
RUN_SAMPLE_LIBRARY = os.environ.get("RUN_SAMPLE_LIBRARY", "true").lower() in {"1", "true", "yes"}
ENABLE_PLOT = os.environ.get("ENABLE_PLOT", "false").lower() in {"1", "true", "yes"}
