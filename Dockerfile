# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1

WORKDIR /opt/shimpz-assistant
RUN install -d -o 10001 -g 10001 -m 0555 /opt/shimpz-assistant/assistant /opt/shimpz-assistant/help

COPY --chmod=0444 requirements.lock ./requirements.lock
RUN PIP_ROOT_USER_ACTION=ignore python3 -m pip install --disable-pip-version-check --no-cache-dir \
        --only-binary=:all: --require-hashes --requirement requirements.lock \
    && rm -rf /root/.cache

COPY --chown=10001:10001 --chmod=0444 GENESIS.md CHANGELOG.md shimpz.toml ./
COPY --chown=10001:10001 --chmod=0444 help/HELP-*.md ./help/
COPY --chown=10001:10001 --chmod=0444 assistant/__init__.py assistant/main.py assistant/cloudflare_api.py ./assistant/
COPY --chown=10001:10001 --chmod=0555 assistant/rpc.py /usr/local/bin/shimpz-assistant-rpc

ENV HOST=0.0.0.0 \
    PORT=8080 \
    PYTHONPATH=/opt/shimpz-assistant \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
EXPOSE 8080

LABEL org.opencontainers.image.source="https://github.com/TheShimpz/shimpz-cloudflare" \
      org.opencontainers.image.version="0.1.3" \
      org.shimpz.assistant.id="shimpz-cloudflare" \
      org.shimpz.assistant.api="1"

ENTRYPOINT ["python3", "-m", "assistant.main"]
