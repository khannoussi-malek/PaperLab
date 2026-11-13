FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv

WORKDIR /voice
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY server.py NOTICE ./

RUN useradd --system --no-user-group --gid nogroup --home-dir /voice --shell /usr/sbin/nologin voice \
    && mkdir -p /voice/models \
    && chown voice /voice/models
USER voice

ENV VOICE_HOST=0.0.0.0 VOICE_MODELS_DIR=/voice/models
EXPOSE 8791
CMD ["/voice/.venv/bin/python", "server.py"]
