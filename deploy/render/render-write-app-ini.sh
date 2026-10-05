#!/bin/sh
set -eu

target="${1:-/repos/gitea/custom/conf/app.ini}"
root_url="${GRUND_PUBLIC_ORIGIN:-${GITEA_ROOT_URL:-}}"
root_url="${root_url%/}"
port="${PORT:-10000}"
app_name="${APP_NAME:-Nordman Grund}"

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
schema="${GITEA__database__SCHEMA:-gitea}"
ssl_mode="${GITEA__database__SSL_MODE:-require}"

mkdir -p "$(dirname "$target")"
umask 077
cat >"$target" <<EOF
APP_NAME = $app_name
RUN_MODE = prod

[server]
DOMAIN = $domain
ROOT_URL = $root_url/
HTTP_ADDR = 0.0.0.0
HTTP_PORT = $port
APP_DATA_PATH = /repos/gitea
START_SSH_SERVER = false
DISABLE_SSH = true

[database]
DB_TYPE = postgres
HOST = $host:$dbport
NAME = $name
USER = $user
PASSWD = $pass
SCHEMA = $schema
SSL_MODE = $ssl_mode

[repository]
ROOT = /repos/git/repositories

[lfs]
PATH = /repos/git/lfs

[log]
ROOT_PATH = /repos/gitea/log

[security]
INSTALL_LOCK = true

[service]
DISABLE_REGISTRATION = false
EOF
chmod 600 "$target"
