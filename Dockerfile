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

# Tectonic, pinned and checked, with its package cache warmed by compiling main.tex of every template folder in
# manuscript_templates, and warm-packages.tex (common packages; not a template). Compiles only ever read this cache
# (TECTONIC_ONLY_CACHED), so acmart's ~20 s cold start is already paid and nothing is downloaded at compile time.
FROM python:3.12-slim AS tex
ARG TARGETARCH
ENV TECTONIC_CACHE_DIR=/tectonic-cache
RUN python - <<'PY'
import hashlib, os, tarfile, urllib.request
VERSION = "0.17.0"
SHA256 = {
    "x86_64": "8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7",
    "aarch64": "b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8",
}
arch = {"amd64": "x86_64", "arm64": "aarch64"}[os.environ["TARGETARCH"]]
asset = f"tectonic-{VERSION}-{arch}-unknown-linux-musl.tar.gz"
data = urllib.request.urlopen(
    f"https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40{VERSION}/{asset}", timeout=120
).read()
assert hashlib.sha256(data).hexdigest() == SHA256[arch], "tectonic archive checksum mismatch"
open("/tmp/tectonic.tgz", "wb").write(data)
with tarfile.open("/tmp/tectonic.tgz") as tar:
    tar.extract("tectonic", "/usr/local/bin")
PY
COPY backend/app/manuscript_templates /templates
RUN for t in /templates/*/; do \
      d=$(mktemp -d) && cp -R "$t". "$d" && cp /templates/warm.bib "$d/paperlab.bib" \
      && (cd "$d" && tectonic -X compile main.tex) || exit 1; \
    done \
    && d=$(mktemp -d) && cd "$d" && cp /templates/warm-packages.tex main.tex && tectonic -X compile main.tex \
    && printf '\\documentclass{article}\\usepackage{verbatim}\\begin{document}\n\\begin{verbatim}\nx\n\\end{verbatim}\n\\end{document}\n' > main.tex \
    && tectonic -X compile main.tex && rm -rf /tmp/* \
    && chmod -R u=rwX,go=rX /tectonic-cache

# Runtime: the environment first, then the code, so an update that changes only code downloads only the last layers.
# No search model: it is downloaded into the models volume when the user chooses it.
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/khannoussi-malek/PaperLab" \
      org.opencontainers.image.description="PaperLab, a local-first research reader" \
      org.opencontainers.image.licenses="Apache-2.0"
COPY --from=deps /venv /venv
COPY --from=tex /usr/local/bin/tectonic /usr/local/bin/tectonic
# Manuscripts compile as `tex` (TECTONIC_USER), an account with no home and no write access to anything of ours.
RUN groupadd --system --gid 999 tex \
    && useradd --system --uid 999 --gid 999 --no-create-home --shell /usr/sbin/nologin tex
# The package cache is root's and read-only to tex (dirs 755, files 644): a project's \openout can't rewrite a package
# another project then loads. No volume: the cache lives in the image, so an update brings its warm set.
COPY --from=tex /tectonic-cache /tectonic-cache
ENV TECTONIC_CACHE_DIR=/tectonic-cache
ENV TECTONIC_ONLY_CACHED=1
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 FRONTEND_DIST=/app/web
WORKDIR /src
COPY backend/ ./
COPY --from=web /web/dist /app/web
# Tectonic runs as `tex`, which must not read the app's code (an `\input` of a relative path reads anything its user can).
RUN chmod 750 /src
