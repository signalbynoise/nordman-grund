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

config=/repos/gitea/custom/conf/app.ini

mkdir -p /repos/gitea/custom/conf /repos/gitea/log /repos/git/repositories /repos/git/lfs
/usr/local/bin/render-write-app-ini.sh "$config"
chown -R git:git /repos

su -p -s /bin/sh git -c "/usr/local/bin/gitea migrate --config \"$config\""
exec su -p -s /bin/sh git -c "exec /usr/local/bin/gitea web --config \"$config\""
