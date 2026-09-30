FROM python:3.12-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned installer) for reproducible dependency sync.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Cloud Agent runs application commands as ubuntu.
RUN useradd -m -s /bin/bash ubuntu \
    && mkdir -p /home/ubuntu/.local/bin \
    && cp /root/.local/bin/uv /home/ubuntu/.local/bin/uv \
    && cp /root/.local/bin/uvx /home/ubuntu/.local/bin/uvx \
    && chown -R ubuntu:ubuntu /home/ubuntu/.local

USER ubuntu
WORKDIR /home/ubuntu
