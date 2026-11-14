# syntax=docker/dockerfile:1
# Build context: repo root. `docker build -f deploy/worker.Dockerfile .`

FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Dependencies only: cached until pyproject.toml/uv.lock change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock ./
COPY pipeline ./pipeline
COPY worker ./worker
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

RUN useradd --uid 10001 --create-home app && mkdir -p /models && chown app /models
USER app
ENV PATH="/app/.venv/bin:$PATH" \
    WORKER_HOST=0.0.0.0 \
    WORKER_PORT=8001 \
    HF_HOME=/models \
    TOKENIZERS_PARALLELISM=false
EXPOSE 8001
CMD ["python", "-m", "worker"]
