FROM node:24.16.0-alpine

RUN apk upgrade --no-cache
RUN apk add --no-cache jemalloc ffmpeg python3 py3-pip curl tar coreutils
ENV LD_PRELOAD=/usr/lib/libjemalloc.so.2

COPY --from=ghcr.io/astral-sh/uv:0.9.5-python3.12-alpine /usr/local/bin/uv /usr/local/bin/uvx /bin/

ARG NODE_MAX_OLD_SPACE_SIZE=6144
ARG NPM_CI_TIMEOUT_SECONDS=1500
ARG NPM_CI_ATTEMPTS=2

RUN mkdir -p /app && chown node:node /app
WORKDIR /app

COPY deploy/runtime/fetch-source.mjs deploy/runtime/materialize-source.mjs deploy/runtime/fetch-archive.mjs /runtime/

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

USER node

RUN node /runtime/fetch-source.mjs --out /app

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
ARG NODE_RUNTIME_MAX_OLD_SPACE_SIZE=384
ENV NODE_OPTIONS=--max-old-space-size=${NODE_RUNTIME_MAX_OLD_SPACE_SIZE}
CMD ["npm", "run", "backend"]
