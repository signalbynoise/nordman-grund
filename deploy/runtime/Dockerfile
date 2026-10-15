FROM node:24.16.0-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tar \
    coreutils \
    ffmpeg \
    git \
    bubblewrap \
    python3 \
    python3-venv \
    python3-pip \
    gcc \
    libc6-dev \
    libjemalloc2 \
  && ln -sf /usr/lib/*-linux-gnu/libjemalloc.so.2 /usr/lib/libjemalloc.so.2 \
  && rm -rf /var/lib/apt/lists/*
ENV LD_PRELOAD=/usr/lib/libjemalloc.so.2

COPY --from=ghcr.io/astral-sh/uv:0.9.5-python3.12-bookworm-slim /usr/local/bin/uv /usr/local/bin/uvx /bin/

# Install Temporal Server CLI (v1.5.1 linux amd64)
RUN curl -fsSL https://github.com/temporalio/cli/releases/download/v1.5.1/temporal_cli_1.5.1_linux_amd64.tar.gz -o /tmp/temporal.tar.gz \
  && tar -xzf /tmp/temporal.tar.gz -C /usr/local/bin temporal \
  && chmod 0755 /usr/local/bin/temporal \
  && rm -f /tmp/temporal.tar.gz

# Install OpenHands SDK v1.54.0 + OpenHands Tools in isolated runtime venv
RUN uv venv /opt/openhands-venv --python python3 \
  && uv pip install --python /opt/openhands-venv/bin/python --no-cache openhands-sdk==1.54.0 openhands-tools==1.54.0 \
  && chmod -R a+rX /opt/openhands-venv

COPY deploy/runtime/nordman-linux-sandbox.c /tmp/nordman-linux-sandbox.c
RUN gcc -O2 -Wall /tmp/nordman-linux-sandbox.c -o /usr/local/bin/nordman-linux-sandbox \
  && chmod 0755 /usr/local/bin/nordman-linux-sandbox \
  && rm -f /tmp/nordman-linux-sandbox.c

ARG NODE_MAX_OLD_SPACE_SIZE=6144
ARG NPM_CI_TIMEOUT_SECONDS=1500
ARG NPM_CI_ATTEMPTS=2

RUN mkdir -p /app && chown node:node /app
WORKDIR /app

COPY deploy/runtime/fetch-source.mjs deploy/runtime/materialize-source.mjs deploy/runtime/fetch-archive.mjs deploy/runtime/source-revision.mjs /runtime/

ARG GRUND_URL
ARG GRUND_DEPLOY_TOKEN
ARG GRUND_OWNER
ARG GRUND_NAME
ARG GRUND_SOURCE_REVISION=unknown
ENV GRUND_URL=$GRUND_URL
ENV GRUND_DEPLOY_TOKEN=$GRUND_DEPLOY_TOKEN
ENV GRUND_OWNER=$GRUND_OWNER
ENV GRUND_NAME=$GRUND_NAME
ENV GRUND_SOURCE_REVISION=$GRUND_SOURCE_REVISION
ENV NORDMAN_OPENHANDS_PYTHON=/opt/openhands-venv/bin/python

USER node

RUN echo "grund-source-revision ${GRUND_SOURCE_REVISION}" \
 && node /runtime/fetch-source.mjs --out /app

RUN \
    touch .env ; \
    mkdir -p /app/client/public/images /app/logs /app/uploads /app/skill /app/data ; \
    chmod 1777 /app/data ; \
    npm config set fetch-retry-maxtimeout 600000 ; \
    npm config set fetch-retries 5 ; \
    npm config set fetch-retry-mintimeout 15000 ; \
    attempt=1 ; \
    until timeout "$NPM_CI_TIMEOUT_SECONDS" npm ci --no-audit ; do \
        status=$? ; \
        if [ "$attempt" -ge "$NPM_CI_ATTEMPTS" ]; then \
            exit "$status" ; \
        fi ; \
        echo "npm ci failed; retrying" ; \
        attempt=$((attempt + 1)) ; \
        npm cache clean --force || true ; \
        sleep 10 ; \
    done

RUN \
    NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE}" npm run frontend; \
    npm prune --production; \
    npm cache clean --force

EXPOSE 3080
ENV HOST=0.0.0.0
ARG NODE_RUNTIME_MAX_OLD_SPACE_SIZE=1536
ENV NODE_OPTIONS=--max-old-space-size=${NODE_RUNTIME_MAX_OLD_SPACE_SIZE}
CMD ["npm", "run", "backend"]
