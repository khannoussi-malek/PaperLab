# The release image: the API, the worker and the built frontend in one, for the desktop app and the two-command install.
# Build context: the repository root (see .dockerignore). Development keeps backend/Dockerfile and frontend/Dockerfile.

# Stage 1: the frontend, from the committed src/api/schema.d.ts. Not npm's own build script: its prebuild regenerates
# the types from a running API, which a build doesn't have.
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx tsc -b && npx vite build

# Stage 2: the Python environment, as backend/Dockerfile builds it. Rebuilt only when pyproject.toml or uv.lock change.
FROM python:3.12-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /src
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# Runtime: the environment first, then the code, so an update that changes only code downloads only the last layers.
# No search model: it is downloaded into the models volume when the user chooses it.
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/khannoussi-malek/PaperLab" \
      org.opencontainers.image.description="PaperLab, a local-first research reader" \
      org.opencontainers.image.licenses="Apache-2.0"
COPY --from=deps /venv /venv
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 FRONTEND_DIST=/app/web
WORKDIR /src
COPY backend/ ./
COPY --from=web /web/dist /app/web
