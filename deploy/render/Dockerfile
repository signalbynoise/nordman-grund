# syntax=docker/dockerfile:1
FROM docker.io/gitea/gitea:1.27.3

COPY deploy/render/render-write-app-ini.sh /usr/local/bin/render-write-app-ini.sh
COPY deploy/render/entrypoint.sh /usr/local/bin/nordman-entrypoint.sh
RUN chmod +x /usr/local/bin/nordman-entrypoint.sh /usr/local/bin/render-write-app-ini.sh

ENTRYPOINT ["/usr/local/bin/nordman-entrypoint.sh"]
