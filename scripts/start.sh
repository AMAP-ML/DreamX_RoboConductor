#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
mkdir -p .run
if [[ -f .run/server.pid ]]; then
  PID="$(cat .run/server.pid)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    echo "PID $PID still exists; inspect or run scripts/stop.sh first." >&2
    exit 1
  fi
  rm -f .run/server.pid
fi
SHOWCASE_HOST="${SHOWCASE_HOST:-127.0.0.1}"
SHOWCASE_PORT="${SHOWCASE_PORT:-8098}"
# Bind in serve.py itself; an occupied port makes this process fail without touching its owner.
PID="$(python3 - "$ROOT" "$SHOWCASE_HOST" "$SHOWCASE_PORT" <<'PY'
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
with (root / '.run/server.log').open('ab', buffering=0) as log:
    server = subprocess.Popen(
        [sys.executable, str(root / 'serve.py'), '--host', sys.argv[2],
         '--port', sys.argv[3], '--directory', str(root / 'dist')],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
print(server.pid)
PY
)"
echo "$PID" > .run/server.pid
sleep 1
if ! kill -0 "$PID" 2>/dev/null; then
  rm -f .run/server.pid
  cat .run/server.log >&2
  exit 1
fi
echo "Started PID $PID at http://$SHOWCASE_HOST:$SHOWCASE_PORT (log: $ROOT/.run/server.log)"
