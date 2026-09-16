#!/usr/bin/env bash
# Seeded, repeatable local development startup. No external data APIs are used.
set -euo pipefail
HYHQ_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == '--sqlite' ]]; then
  export ENV=development HYHQ_USE_SQLITE=1
  shift
fi
if [[ "${1:-}" == '--help' ]]; then
  printf '%s\n' 'Usage: scripts/dev.sh [--sqlite] [127.0.0.1:8000]' \
    '默认使用 PostgreSQL；--sqlite 仅用于本机开发。'
  exit 0
fi
"$HYHQ_ROOT/scripts/manage.sh" migrate --noinput
"$HYHQ_ROOT/scripts/manage.sh" seed_demo
exec "$HYHQ_ROOT/scripts/manage.sh" runserver "${1:-127.0.0.1:8000}"
