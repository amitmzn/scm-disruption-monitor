# scm-disruption-monitor

Monitor supply-chain disruption signals using [Laya](https://laya.studio/) typed decisions (`POST /v1/systemone`). The repository description references Control Tower-style evaluation workflows; this starter focuses on the core disruption assessment CLI.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
bash scripts/cloud-agent-install.sh
```

## Commands

```bash
# Bundled sample events (offline heuristics)
uv run scm-monitor analyze --sample

# Laya API connectivity check (no API key required)
uv run scm-monitor health

# Live Laya decisions (requires LAYA_API_KEY)
export LAYA_API_KEY=lsk_live_...
uv run scm-monitor analyze --sample --live
```

## Tests and lint

```bash
uv run pytest
uv run ruff check .
```

## Secrets

| Name | Purpose |
| --- | --- |
| `LAYA_API_KEY` | Bearer token for `https://api.laya.studio/v1/systemone` when using `--live` |

Optional: `LAYA_BASE_URL` to point at self-hosted `laya-serve`.
