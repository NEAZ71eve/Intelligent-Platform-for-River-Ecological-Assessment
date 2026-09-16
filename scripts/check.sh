#!/usr/bin/env bash
set -euo pipefail
HYHQ_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == '--sqlite' ]]; then
  export ENV=development HYHQ_USE_SQLITE=1
  shift
fi
"$HYHQ_ROOT/scripts/manage.sh" check
"$HYHQ_ROOT/scripts/manage.sh" makemigrations --check --dry-run
"$HYHQ_ROOT/scripts/manage.sh" test "$@"
