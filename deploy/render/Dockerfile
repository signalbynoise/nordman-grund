# syntax=docker/dockerfile:1
FROM docker.io/gitea/gitea:1.28.0-rootless

USER root
COPY deploy/render/render-env.mjs /usr/local/bin/render-env.mjs
COPY deploy/render/entrypoint.sh /usr/local/bin/nordman-entrypoint.sh
RUN chmod +x /usr/local/bin/nordman-entrypoint.sh /usr/local/bin/render-env.mjs
USER 1000

ENTRYPOINT ["/usr/local/bin/nordman-entrypoint.sh"]
