#!/usr/bin/env bash
# ClipDock one-click deploy for Ubuntu Server 24.04 (2 vCPU / 4 GB).
#
#   sudo bash deploy/deploy.sh              # install/update the app + Nginx
#   sudo bash deploy/deploy.sh --no-nginx   # app only (BaoTa owns Nginx)
#
# Re-running the script is safe: it updates code and dependencies, and never
# overwrites /opt/clipdock/.env.
set -euo pipefail

REPO_URL="${CLIPDOCK_REPO:-https://github.com/kami519/PROPOSAL.git}"
APP_DIR="${CLIPDOCK_DIR:-/opt/clipdock}"
APP_USER="clipdock"
PYTHON_BIN="/usr/bin/python3.12"
SETUP_NGINX=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir) APP_DIR="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --no-nginx|--bt) SETUP_NGINX=0; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "please run as root: sudo bash deploy/deploy.sh" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
log "install system packages"
apt-get update -y
apt-get install -y python3.12 python3.12-venv python3-pip git curl ca-certificates
if [[ "$SETUP_NGINX" -eq 1 ]]; then
  apt-get install -y nginx
fi
if ! command -v node >/dev/null 2>&1; then
  apt-get install -y nodejs npm
fi

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "create service user $APP_USER"
  useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR"
if [[ -d "$APP_DIR/.git" ]]; then
  log "update source"
  git -C "$APP_DIR" fetch --depth 1 origin main
  git -C "$APP_DIR" checkout --force main
  git -C "$APP_DIR" reset --hard origin/main
else
  log "clone source"
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

log "install python dependencies"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  sudo -u "$APP_USER" "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
fi
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u "$APP_USER" env MAKEFLAGS="-j1" "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

log "build frontend"
( cd "$APP_DIR/frontend" && npm ci --no-audit --no-fund && npm run build )
chown -R "$APP_USER:$APP_USER" "$APP_DIR/frontend/dist"

log "prepare config"
if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/deploy/server.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  echo "created $APP_DIR/.env, fill SUMMARY_API_KEY then: systemctl restart clipdock"
else
  echo "keep existing $APP_DIR/.env"
fi
mkdir -p "$APP_DIR/data/cache" "$APP_DIR/data/library"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/data"

log "install systemd unit"
install -m 644 "$APP_DIR/deploy/clipdock.service" /etc/systemd/system/clipdock.service
systemctl daemon-reload
systemctl enable clipdock
systemctl restart clipdock

if [[ "$SETUP_NGINX" -eq 1 ]]; then
  log "configure nginx (standalone mode)"
  install -m 644 "$APP_DIR/deploy/nginx-clipdock.conf" /etc/nginx/sites-available/clipdock
  ln -sf /etc/nginx/sites-available/clipdock /etc/nginx/sites-enabled/clipdock
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl enable nginx
  systemctl restart nginx
else
  log "skip nginx (managed by BaoTa or by hand)"
  echo "reverse proxy config: $APP_DIR/deploy/nginx-clipdock.conf"
fi

log "wait for service"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

log "health check"
curl -fsS http://127.0.0.1:8000/api/health || true
echo

cat <<EOF

Deploy finished.
  App URL    http://<server-ip>:8000/
  Tasks      http://<server-ip>:8000/#/tasks
  Config     $APP_DIR/.env
  Logs       journalctl -u clipdock -f

Next:
  1. Edit $APP_DIR/.env and fill SUMMARY_API_KEY.
  2. systemctl restart clipdock
EOF