#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PIDFILE="$ROOT/.run/server.pid"
[[ -f "$PIDFILE" ]] || { echo 'No PID file; already stopped.'; exit 0; }
PID="$(cat "$PIDFILE")"
[[ "$PID" =~ ^[0-9]+$ ]] || { echo 'Invalid PID file; refusing.' >&2; exit 1; }
if ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PIDFILE"
  echo 'Already stopped.'
  exit 0
fi
# Match the actual interpreter argument, not a substring in an unrelated command.
python3 - "$PID" "$ROOT/serve.py" <<'PY'
import os, subprocess, sys
pid, expected = sys.argv[1:]
try:
    if os.path.exists(f'/proc/{pid}/cmdline'):
        args = open(f'/proc/{pid}/cmdline', 'rb').read().decode().split('\0')
    else:
        import shlex
        args = shlex.split(subprocess.check_output(['ps', '-p', pid, '-o', 'command='], text=True).strip())
    if len(args) < 2 or os.path.realpath(args[1]) != expected or 'python' not in os.path.basename(args[0]).lower():
        raise ValueError('PID does not belong to this server')
except Exception as exc:
    sys.exit(f'Refusing to stop PID {pid}: {exc}')
PY
kill -TERM "$PID"
for _ in {1..50}; do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PIDFILE"
    echo "Stopped PID $PID"
    exit 0
  fi
  sleep 0.1
done
echo "SIGTERM sent to PID $PID; still present, inspect before retrying." >&2
exit 1
