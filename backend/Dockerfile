# Stage 1: dependencies only. Rebuilt when pyproject/uv.lock change, never on code edits.
FROM python:3.12-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# Tectonic, pinned and checked, with its package cache warmed by compiling every manuscript template: the first user
# compile then needs no network, and acmart's ~20 s cold start is already paid.
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
COPY app/manuscript_templates /templates
RUN for t in /templates/*.tex; do \
      d=$(mktemp -d) && cp "$t" "$d/main.tex" && cp /templates/warm.bib "$d/paperlab.bib" \
      && (cd "$d" && tectonic -X compile main.tex) || exit 1; \
    done && rm -rf /tmp/*

# Stage 3: runtime. api and worker share this image with different commands.
FROM python:3.12-slim
COPY --from=deps /venv /venv
COPY --from=tex /usr/local/bin/tectonic /usr/local/bin/tectonic
# Manuscripts compile as `tex` (TECTONIC_USER), an account with no home and no write access to anything of ours.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin tex
COPY --from=tex --chown=tex:tex /tectonic-cache /tectonic-cache
ENV TECTONIC_CACHE_DIR=/tectonic-cache
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /src
COPY . .
# ponytail: /src is a host bind mount here, so its modes can't be tightened and `tex` can read the code; the dev stack
# accepts that. The release image doesn't: it makes /src unreadable to other users.
