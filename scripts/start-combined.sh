#!/bin/sh
# Entrypoint for the single-container image: uvicorn on a private port, nginx on $PORT.
set -e

# Cloud Run may hand us a port other than 8080; rewrite nginx's listen to match.
PORT="${PORT:-8080}"
sed -i "s/listen 8080;/listen ${PORT};/" /etc/nginx/conf.d/default.conf

uvicorn main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

# Block until uvicorn is actually accepting connections BEFORE nginx binds $PORT.
#
# This ordering is load-bearing on Cloud Run. The startup probe targets $PORT, so if
# nginx binds first the probe passes instantly, the container is declared ready, and
# CPU is throttled — while uvicorn is still importing google-adk in the background.
# It then crawls, never binds, and every API call returns nginx 502 "Connection
# refused" against a container Cloud Run believes is healthy. Holding nginx back
# keeps the probe failing until the API is genuinely up.
python - <<'PY'
import socket, sys, time

for _ in range(240):
    sock = socket.socket()
    sock.settimeout(1)
    try:
        sock.connect(("127.0.0.1", 8000))
        sys.exit(0)
    except OSError:
        time.sleep(1)
    finally:
        sock.close()
sys.exit(1)
PY

nginx -g 'daemon off;' &
NGINX_PID=$!

terminate() {
    kill "$API_PID" "$NGINX_PID" 2>/dev/null || true
    exit 0
}
trap terminate TERM INT

# Exit as soon as EITHER process exits, so a dead backend takes the instance down
# instead of leaving nginx serving a site whose every API call fails.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$NGINX_PID" 2>/dev/null; do
    sleep 2
done

kill "$API_PID" "$NGINX_PID" 2>/dev/null || true
exit 1
