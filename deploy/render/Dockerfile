# syntax=docker/dockerfile:1
FROM docker.io/gitea/gitea:1.27.3

USER root
RUN apk add --no-cache python3

COPY deploy/render/render-write-app-ini.sh /usr/local/bin/render-write-app-ini.sh
COPY deploy/render/entrypoint.sh /usr/local/bin/nordman-entrypoint.sh
COPY deploy/render/release_revision.py /usr/local/bin/nordman-release-revision.py
COPY deploy/render/release-on-push.sh /usr/local/bin/nordman-release-on-push.sh
RUN chmod 755 /usr/local/bin/nordman-entrypoint.sh /usr/local/bin/render-write-app-ini.sh /usr/local/bin/nordman-release-on-push.sh /usr/local/bin/nordman-release-revision.py

ENTRYPOINT ["/usr/local/bin/nordman-entrypoint.sh"]
