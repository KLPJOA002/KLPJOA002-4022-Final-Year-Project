#!/bin/sh
# Dev helper: start/stop a test UI server on port 8099 with an isolated state folder.
#   tools/dev_server.sh start | stop
cd "$(dirname "$0")/.." || exit 1
STATE="$PWD/examples/_ui_state"; PID="$STATE/server.pid"; mkdir -p "$STATE"
case "$1" in
  start)
    tools/host.sh env RSPLOT_STATE_DIR="$STATE" sh -c \
      'nohup python -m rsplot.ui.app --port 8099 --no-browser > "$RSPLOT_STATE_DIR/server.log" 2>&1 & echo $! > "$RSPLOT_STATE_DIR/server.pid"'
    for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:8099/ && break; sleep 1; done
    echo "started pid $(cat "$PID")";;
  stop)
    [ -f "$PID" ] && tools/host.sh kill "$(cat "$PID")" 2>/dev/null; rm -f "$PID"
    for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8099/ || break; sleep 0.5; done
    echo stopped;;
esac
