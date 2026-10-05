# syntax=docker/dockerfile:1
FROM docker.io/gitea/gitea:1.27.3-rootless

USER root
COPY deploy/render/render-env.sh /usr/local/bin/render-env.sh
COPY deploy/render/entrypoint.sh /usr/local/bin/nordman-entrypoint.sh
RUN chmod +x /usr/local/bin/nordman-entrypoint.sh /usr/local/bin/render-env.sh
USER 1000

ENTRYPOINT ["/usr/local/bin/nordman-entrypoint.sh"]
