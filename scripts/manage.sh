#!/usr/bin/env bash
# Run from any directory. Environment and credentials are loaded by Django.
set -euo pipefail
HYHQ_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
HYHQ_PYTHON="${HYHQ_PYTHON:-$HYHQ_ROOT/.venv/bin/python}"
if [[ ! -x "$HYHQ_PYTHON" ]]; then
  printf '%s\n' '缺少项目 Python 虚拟环境，请先按 deploy/README.md 安装依赖。' >&2
  exit 1
fi
cd "$HYHQ_ROOT/backend"
exec "$HYHQ_PYTHON" manage.py "$@"
