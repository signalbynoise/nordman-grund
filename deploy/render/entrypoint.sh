#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required for Nordman Grund on Render" >&2
  exit 1
fi

if [ -z "${GRUND_PUBLIC_ORIGIN:-}" ] && [ -z "${GITEA_ROOT_URL:-}" ]; then
  echo "GRUND_PUBLIC_ORIGIN or GITEA_ROOT_URL is required" >&2
  exit 1
fi

mkdir -p /repos/gitea/conf /repos/gitea/log /repos/git/repositories /repos/git/lfs
chown -R git:git /repos

eval "$(/usr/local/bin/render-env.sh)"

exec su -p -s /bin/sh git -c 'exec /usr/bin/entrypoint "$@"' -- "$@"
