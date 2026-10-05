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
home=/repos/gitea/home

mkdir -p /repos/gitea/custom/conf /repos/gitea/log /repos/git/repositories /repos/git/lfs "$home"
/usr/local/bin/render-write-app-ini.sh "$config"
chown -R git:git /repos

run_git() {
  # su -p keeps DATABASE_URL; HOME must not be /root or libpq breaks SSL on migrate.
  su -p -s /bin/sh git -c "export HOME=\"$home\" PGSSLMODE=require; $*"
}

run_git "/usr/local/bin/gitea migrate --config \"$config\""
exec su -p -s /bin/sh git -c "export HOME=\"$home\" PGSSLMODE=require; exec /usr/local/bin/gitea web --config \"$config\""
