# 3.14, because `pyproject.toml` declares `requires-python = ">=3.14"` and `uv.lock` pins cp314
# wheels: `uv sync --frozen` on 3.12 fails on the interpreter constraint before it reaches a wheel.
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# `src` before the sync: the project installs itself, so `version("ns-api-gateway")` (main.py) has a
# distribution to read. `--no-dev` names the one declared group; there is no `test` group.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Only the config tree: the package is installed in the venv, and the app imports itself absolutely
# (`nativespeaker.api...`), so a second copy of the sources under /app would shadow nothing usefully.
# `config_dir` defaults to `config/` relative to the working directory (config.py).
COPY config ./config/

# Create non-root user for security. uid 1000 matches the chart's `runAsUser`.
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# No HEALTHCHECK: the kubelet does not read one, and the chart already probes /health/ready.
CMD ["uvicorn", "nativespeaker.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
