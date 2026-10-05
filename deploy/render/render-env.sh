#!/bin/sh
set -eu

root_url="${GRUND_PUBLIC_ORIGIN:-${GITEA_ROOT_URL:-}}"
root_url="${root_url%/}"
port="${PORT:-10000}"

case "$DATABASE_URL" in
  postgres://*|postgresql://*)
    ;;
  *)
    echo "DATABASE_URL must be a postgres URL" >&2
    exit 1
    ;;
esac

db="${DATABASE_URL#postgres://}"
db="${db#postgresql://}"
userpass="${db%%@*}"
hostpath="${db#*@}"
user="${userpass%%:*}"
pass="${userpass#*:}"
hostport="${hostpath%%/*}"
name="${hostpath#*/}"
host="${hostport%%:*}"
dbport="${hostport#*:}"
if [ "$dbport" = "$hostport" ]; then
  dbport=5432
fi

domain=$(printf '%s' "$root_url" | sed -E 's#^https?://([^/]+).*$#\1#')

cat <<EOF
export GITEA__server__DOMAIN=$domain
export GITEA__server__ROOT_URL=$root_url/
export GITEA__server__HTTP_ADDR=0.0.0.0
export GITEA__server__HTTP_PORT=$port
export GITEA__server__APP_DATA_PATH=/data/gitea
export GITEA__repository__ROOT=/data/git/repositories
export GITEA__lfs__PATH=/data/git/lfs
export GITEA__database__DB_TYPE=postgres
export GITEA__database__HOST=$host:$dbport
export GITEA__database__NAME=$name
export GITEA__database__USER=$user
export GITEA__database__PASSWD=$pass
export GITEA__database__SCHEMA=${GITEA__database__SCHEMA:-gitea}
export GITEA__database__SSL_MODE=${GITEA__database__SSL_MODE:-require}
export GITEA__security__INSTALL_LOCK=${GITEA__security__INSTALL_LOCK:-true}
export GITEA__service__DISABLE_REGISTRATION=${GITEA__service__DISABLE_REGISTRATION:-false}
export GITEA__mailer__ENABLED=${GITEA__mailer__ENABLED:-false}
EOF

if [ -n "${APP_NAME:-}" ]; then
  printf 'export GITEA__other__APP_NAME=%s\n' "$APP_NAME"
fi
