# syntax=docker/dockerfile:1
FROM docker.io/gitea/gitea:1.27.3

COPY deploy/render/render-env.sh /usr/local/bin/render-env.sh
COPY deploy/render/entrypoint.sh /usr/local/bin/nordman-entrypoint.sh
RUN chmod +x /usr/local/bin/nordman-entrypoint.sh /usr/local/bin/render-env.sh \
  && ln -sfn /repos /data

ENTRYPOINT ["/usr/local/bin/nordman-entrypoint.sh"]
CMD ["/usr/local/bin/gitea", "web"]
