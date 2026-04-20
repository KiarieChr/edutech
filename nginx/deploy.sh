#!/usr/bin/env bash
# deploy.sh  —  Full deployment script for Fahari Academia on a Linux VPS
# Run as the `deploy` user.  Edit the variables at the top before first use.
# Usage:  bash deploy.sh

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
DEPLOY_DIR="/home/deploy/fahari_academia"
FRONTEND_DIR="/var/www/fahari_academia"
REPO_BACKEND="git@github.com:YOUR_ORG/edutech.git"
REPO_FRONTEND="git@github.com:YOUR_ORG/fahari-afrontend.git"
VENV="$DEPLOY_DIR/venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

# ── Backend ───────────────────────────────────────────────────────────────────
echo "==> Pulling backend…"
if [ -d "$DEPLOY_DIR/.git" ]; then
    git -C "$DEPLOY_DIR" pull --ff-only
else
    git clone "$REPO_BACKEND" "$DEPLOY_DIR"
fi

echo "==> Installing Python dependencies…"
"$PIP" install --upgrade pip
"$PIP" install -r "$DEPLOY_DIR/requirements.txt"

echo "==> Applying migrations…"
"$PYTHON" "$DEPLOY_DIR/manage.py" migrate --no-input

echo "==> Collecting static files…"
"$PYTHON" "$DEPLOY_DIR/manage.py" collectstatic --no-input

echo "==> Compiling translations…"
"$PYTHON" "$DEPLOY_DIR/manage.py" compilemessages || true

echo "==> Restarting Gunicorn…"
sudo systemctl restart gunicorn_fahari

# ── Frontend ──────────────────────────────────────────────────────────────────
FRONTEND_BUILD="/tmp/fahari_frontend_build"

echo "==> Pulling frontend…"
if [ -d "$FRONTEND_BUILD/.git" ]; then
    git -C "$FRONTEND_BUILD" pull --ff-only
else
    git clone "$REPO_FRONTEND" "$FRONTEND_BUILD"
fi

echo "==> Installing JS dependencies…"
npm --prefix "$FRONTEND_BUILD" ci --silent

echo "==> Building React app…"
npm --prefix "$FRONTEND_BUILD" run build

echo "==> Deploying frontend to $FRONTEND_DIR…"
sudo rsync -a --delete "$FRONTEND_BUILD/dist/" "$FRONTEND_DIR/"

echo "==> Reloading Nginx…"
sudo nginx -t && sudo systemctl reload nginx

echo ""
echo "✅  Deployment complete!"
echo "   Backend:  https://api.royalsoftwares.co.ke"
echo "   Frontend: https://fahari.royalsoftwares.co.ke"
