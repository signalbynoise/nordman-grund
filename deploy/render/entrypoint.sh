#!/bin/sh
set -eu

mkdir -p /repos/gitea/conf /repos/gitea/log /repos/git/repositories /repos/git/lfs

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required for Nordman Grund on Render" >&2
  exit 1
fi

if [ -z "${GRUND_PUBLIC_ORIGIN:-}" ] && [ -z "${GITEA_ROOT_URL:-}" ]; then
  echo "GRUND_PUBLIC_ORIGIN or GITEA_ROOT_URL is required" >&2
  exit 1
fi

eval "$(/usr/local/bin/render-env.sh)"

if [ -x /usr/local/bin/gitea ]; then
  /usr/local/bin/gitea migrate || exit 1
  if [ "${GITEA_BOOTSTRAP_ADMIN:-}" = "true" ] && [ -n "${GITEA_ADMIN_PASSWORD:-}" ]; then
    /usr/local/bin/gitea admin user create \
      --username "${GITEA_ADMIN_USER:-erik}" \
      --email "${GITEA_ADMIN_EMAIL:-erik.lydecker@gmail.com}" \
      --password "$GITEA_ADMIN_PASSWORD" \
      --admin \
      --must-change-password=false 2>/dev/null || true
  fi
fi

if [ -x /usr/local/bin/gitea ]; then
  exec /usr/local/bin/gitea web
fi
if [ -x /usr/bin/entrypoint ]; then
  exec /usr/bin/entrypoint /usr/local/bin/gitea web
fi
echo "gitea binary not found" >&2
exit 127
