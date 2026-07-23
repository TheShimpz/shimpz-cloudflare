# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1

WORKDIR /opt/shimpz-assistant
RUN install -d -o 10001 -g 10001 -m 0555 /opt/shimpz /opt/shimpz/help /opt/shimpz-assistant

COPY --chmod=0444 .build/sdk/shimpz-0.1.0-py3-none-any.whl /tmp/shimpz-0.1.0-py3-none-any.whl
COPY --chmod=0444 assistants/shimpz-cloudflare/requirements.lock ./requirements.lock
RUN PIP_ROOT_USER_ACTION=ignore python3 -m pip install --disable-pip-version-check --no-cache-dir \
        --only-binary=:all: --require-hashes --requirement requirements.lock \
    && python3 -m pip install --disable-pip-version-check --no-cache-dir --no-deps --no-index \
        /tmp/shimpz-0.1.0-py3-none-any.whl \
    && chmod 0555 /usr/local/bin/shimpz-assistant /usr/local/bin/shimpz-assistant-rpc \
    && rm /tmp/shimpz-0.1.0-py3-none-any.whl \
    && rm -rf /root/.cache

COPY --chown=10001:10001 --chmod=0444 assistants/shimpz-cloudflare/GENESIS.md \
    assistants/shimpz-cloudflare/CHANGELOG.md ./
COPY --chown=10001:10001 --chmod=0444 assistants/shimpz-cloudflare/shimpz.toml \
    assistants/shimpz-cloudflare/app.py /opt/shimpz/
COPY --chown=10001:10001 --chmod=0444 assistants/shimpz-cloudflare/help/HELP-*.md /opt/shimpz/help/
RUN shimpz-assistant-contract --app /opt/shimpz/app.py --output /opt/shimpz/shimpz.contract.json \
    && chmod 0444 /opt/shimpz/shimpz.contract.json

ENV HOST=0.0.0.0 \
    PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
EXPOSE 8080

LABEL org.opencontainers.image.source="https://github.com/TheShimpz/shimpz-cloudflare" \
      org.opencontainers.image.version="0.2.0" \
      org.shimpz.assistant.id="shimpz-cloudflare" \
      org.shimpz.assistant.api="1"

ENTRYPOINT ["shimpz-assistant"]
