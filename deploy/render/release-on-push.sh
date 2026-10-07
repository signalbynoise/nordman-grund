#!/bin/sh
# Gitea runs this from hooks/post-receive.d. Git does not pass the service
# environment through, so the credentials live in a root-written file.
set -eu

if [ -z "${RENDER_API_KEY:-}" ] && [ -f "${NORDMAN_RELEASE_ENV:-/repos/gitea/custom/release.env}" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${NORDMAN_RELEASE_ENV:-/repos/gitea/custom/release.env}"
  set +a
fi

exec python3 /usr/local/bin/nordman-release-revision.py
