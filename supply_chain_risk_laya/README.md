# Real-Time Supply Chain Risk & Disruption Monitoring

Manufacturing **Control Tower triage** prototype using **Laya typed decisions** (no free-form LLM text generation) and optional **AG News** unstructured headlines.

This repository folder is designed to live in **Google Drive** and run directly from **Google Colab**.

> **Not production-ready.** This is decision-support research software. Probabilities are **not** guaranteed to be calibrated for your domain until you validate on labelled supply-chain data and keep humans in the loop for high-impact procurement actions.

---

## 1. Business problem

Manufacturing control towers ingest noisy macro and operational alerts (strikes, floods, supplier distress, logistics bottlenecks). Operators need **machine-readable** triage:

1. `disruption_category` (typed choice)
2. `severity_index` (0–3 score)
3. `trigger_backup_sourcing` (yes/no probability + operational trigger)

Downstream targets (future phases): **Business Central**, **Supply Chain Management**, **Microsoft Fabric**, **Power BI**, automated backup-supplier workflows.

**Laya** answers fixed question schemas in one forward pass—structured probabilities, not generated paragraphs.

---

## 2. Architecture

```text
Unstructured alert (news text / Control Tower event)
        ↓
Laya Router.predict(state, questions)
        ↓
Normalized JSON + CSV (Control Tower schema)
        ↓
[Future] Business Central API → Fabric → Power BI → Power Automate / Copilot
```

Core modules:

| File | Role |
| --- | --- |
| `supply_chain_risk_laya.py` | CLI, inference, AG News batch, output writers |
| `config.py` | Thresholds, sample sizes, paths |
| `sample_alerts.json` | Demo/test alert library |
| `tests/test_risk_schema.py` | Deterministic unit tests (no model weights) |

---

## 3. Why Laya?

- **Typed outputs**: `choice`, `score`, `noul` map directly to ERP / analytics columns.
- **Non-autoregressive**: no open-ended text generation for triage decisions.
- **Probabilities returned by the model** (use for ranking/gating, not as calibrated procurement policy without validation).

Verified API (package **laya 0.3.x**):

```python
from laya import Router

router = Router(preload=True)
result = router.predict(state, questions)
# result["answers"][question_id] → choice / score / noul fields
```

If your installed version differs slightly, this project reads the actual answer payload shape from `result["answers"]`.

---

## 4. Why AG News?

[`fancyzhx/ag_news`](https://huggingface.co/datasets/fancyzhx/ag_news) provides large-scale **unstructured news text** with coarse labels:

| Label id | Name |
| --- | --- |
| 0 | World |
| 1 | Sports |
| 2 | Business |
| 3 | Sci/Tech |

We focus on **World + Business** for demos, but **AG News labels are not supply-chain risk labels**. The prototype uses Laya zero-shot typed questions to infer operational risk fields.

### Important AG News limitation

**AG News is a general news classification dataset and is NOT a labelled supply-chain risk dataset.**

- Business/World ≠ automatic supply-chain disruption
- Zero-shot Laya output ≠ validated classification accuracy for your plants/suppliers
- Create domain-specific labelled data before operational automation
- Calibrate probabilities before autonomous procurement
- Keep human approval for high-impact sourcing changes

---

## 5. Installation (local or Colab)

```bash
pip install -r requirements.txt
```

**First Laya run** may download model checkpoints from Hugging Face (large download, CPU or GPU depending on runtime). Plan time and disk accordingly.

Environment overrides (optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SCM_PROJECT_ROOT` | folder containing `config.py` | Project root (Colab/Drive) |
| `BACKUP_SOURCING_THRESHOLD` | `0.70` | Backup trigger cutoff |
| `RELEVANCE_THRESHOLD` | `0.60` | Supply-chain relevance gate |
| `USE_PRELOAD` | `true` | `Router(preload=True)` vs lazy load |
| `AG_NEWS_SAMPLE_SIZE` | `20` | Batch row limit |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## 6. Google Drive + Colab

### Recommended: full notebook

Open **`Supply_Chain_Control_Tower_Laya.ipynb`** in Colab (same folder as this README). It walks through Drive mount, Laya inference, the sample library, optional AG News, charts, saved CSV/JSON, and pytest — without relying on the CLI alone.

1. Copy the entire `supply_chain_risk_laya/` folder to Drive (example: `MyDrive/supply_chain_risk_laya`).
2. In Colab: **File → Open notebook** → Drive → `Supply_Chain_Control_Tower_Laya.ipynb`, or upload the `.ipynb` from this repo.

### Script-only alternative

1. Copy the project folder to Drive.
2. Open a Colab notebook and run:

```python
from google.colab import drive
drive.mount('/content/drive')
```

3. Change to your project folder (**edit the path for your Drive layout**):

```python
import os
os.environ["SCM_PROJECT_ROOT"] = "/content/drive/MyDrive/supply_chain_risk_laya"
%cd "$SCM_PROJECT_ROOT"
```

4. Install dependencies:

```python
!pip install -r requirements.txt
```

5. Run the pipeline:

```python
!python supply_chain_risk_laya.py
```

Alternative:

```python
%run supply_chain_risk_laya.py
```

Optional flags:

```python
!python supply_chain_risk_laya.py --no-preload        # lower memory, slower first inference
!python supply_chain_risk_laya.py --sample-library  # process sample_alerts.json
!python supply_chain_risk_laya.py --ag-news         # AG News batch (limited rows)
!python supply_chain_risk_laya.py --ag-news --plot  # matplotlib summary
```

---

## 7. Example output

```text
=========================================================
SUPPLY CHAIN CONTROL TOWER - LAYA TRIAGE
=========================================================

Alert:
Unionized transport workers at the key regional port...

Supply Chain Relevant : YES
Relevance Probability : 0.97

Disruption Category   : logistics_transport
Category Probability  : 0.94

Severity Index        : 3 / 3

Backup Sourcing Prob. : 0.92
Backup Sourcing       : TRIGGER

Control Tower Priority: CRITICAL

Laya Model            : english
=========================================================
```

Raw Laya JSON is printed for audit/debugging and stored under `raw_laya_response` in JSON output.

---

## 8. Output schema

Files written to `output/` (created automatically):

- `control_tower_results.json` — full structured results
- `control_tower_results.csv` — flattened operational columns for Power BI / Fabric

Priority is a **deterministic demo rule** from severity + backup probability (see `compute_priority()`), not an ML score.

`export_for_business_central()` prepares a REST-ready payload list ( **no API calls** in this prototype).

---

## 9. Performance measurement

The CLI prints:

```text
Initialization time : X.XX sec
Inference time      : X.XXX sec
```

Batch mode prints AG News aggregate timing when enabled. **Do not treat these as universal benchmarks**—Colab CPU/GPU tiers vary widely.

`Router(preload=True)` loads checkpoints up front (faster repeated inference, higher memory). Use `--no-preload` or `USE_PRELOAD=false` on memory-constrained runtimes.

---

## 10. Testing

From the project directory:

```bash
pytest tests/test_risk_schema.py -m "not integration"
```

Optional live integration (downloads/runs Laya weights):

```bash
pytest tests/test_risk_schema.py -m integration
```

---

## 11. Future evolution

| Phase | Focus |
| --- | --- |
| 1 | AG News + Laya prototype (**this repo**) |
| 2 | Curated supply-chain news corpus |
| 3 | Domain-specific labelled dataset |
| 4 | Evaluate accuracy, precision, recall, F1, severity MAE, backup precision, false-trigger rate |
| 5 | Probability calibration |
| 6 | Business Central integration |
| 7 | Microsoft Fabric / Power BI Control Tower |
| 8 | Power Automate / Copilot Agent workflows |

---

## 12. Model risk & limitations

- Prototype triage only—**no automatic supplier actions**
- Laya probabilities should be validated and calibrated before operational automation
- AG News includes many non-supply-chain stories; relevance gating (`is_supply_chain_relevant`) reduces false triggers but is not perfect
- GPU optional; CPU fallback depends on PyTorch build installed with `laya`

---

## 13. Integration readiness (future)

```text
Business Central API
        ↓
Supply Chain Risk Table
        ↓
Microsoft Fabric
        ↓
Power BI Control Tower
        ↓
Power Automate / Copilot Agent
```

Use `export_for_business_central()` output as the starting payload contract.
