#!/usr/bin/env bash
# Generate a complete 48-hour snapshot. Scheduling is optional in M1.
set -euo pipefail
HYHQ_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
HYHQ_PYTHON="${HYHQ_PYTHON:-$HYHQ_ROOT/.venv/bin/python}"
if [[ ! -x "$HYHQ_PYTHON" ]]; then
  printf '%s\n' '缺少项目 Python 虚拟环境。' >&2
  exit 1
fi
HYHQ_START="$("$HYHQ_PYTHON" -c 'from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=47)).isoformat())')"
exec "$HYHQ_ROOT/scripts/manage.sh" generate_simulation --scenario "${1:-normal}" --start "$HYHQ_START" --hours 48 --seed 20260916
