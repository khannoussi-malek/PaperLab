# Stage 1: dependencies only. Rebuilt when pyproject/uv.lock change, never on code edits.
FROM python:3.12-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# Tectonic, pinned and checked, with its package cache warmed by compiling main.tex of every template folder in
# manuscript_templates (twice: the second time with warm-results.tex inserted, so each class fetches the font sizes its
# own tables and charts use), warm-packages.tex and warm-diagram.tex (common packages and the TikZ libraries a
# diagram may load; not templates). Compiles only ever read this cache
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
COPY app/manuscript_templates /templates
RUN for t in /templates/*/; do \
      d=$(mktemp -d) && cp -R "$t". "$d" && cp /templates/warm.bib "$d/paperlab.bib" \
      && (cd "$d" && tectonic -X compile main.tex) \
      && cp /templates/warm-results.tex /templates/warm-figure.png "$d" \
      && awk '/^\\begin\{document\}/ && !d { print "\\usepackage{booktabs,pgfplots,graphicx}"; print "\\pgfplotsset{compat=1.18}"; print; print "\\input{warm-results}"; d = 1; next } { print }' "$d/main.tex" > "$d/results.tex" \
      && (cd "$d" && tectonic -X compile results.tex) || exit 1; \
    done \
    && d=$(mktemp -d) && cd "$d" && cp /templates/warm-packages.tex main.tex && tectonic -X compile main.tex \
    && cp /templates/warm-diagram.tex main.tex && tectonic -X compile main.tex \
    && printf '\\documentclass{article}\\usepackage{verbatim}\\begin{document}\n\\begin{verbatim}\nx\n\\end{verbatim}\n\\end{document}\n' > main.tex \
    && tectonic -X compile main.tex && rm -rf /tmp/* \
    && chmod -R u=rwX,go=rX /tectonic-cache

# Stage 3: runtime. api and worker share this image with different commands.
FROM python:3.12-slim
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
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /src
COPY . .
# ponytail: /src is a host bind mount here, so its modes can't be tightened and `tex` can read the code; the dev stack
# accepts that. The release image doesn't: it makes /src unreadable to other users.
