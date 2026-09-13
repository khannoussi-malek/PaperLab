# Stage 1: dependencies only. Rebuilt when pyproject/uv.lock change, never on code edits.
FROM python:3.12-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# Stage 2: runtime. api and worker share this image with different commands.
FROM python:3.12-slim
COPY --from=deps /venv /venv
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /src
COPY . .
