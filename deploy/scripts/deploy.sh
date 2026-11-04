#!/usr/bin/env bash
# ==============================================================================
# deploy.sh
# Automated deployment script for Academia on Linux production.
# ==============================================================================

set -euo pipefail

ACADEMIA_DIR="/var/www/academia"
BACKEND_DIR="${ACADEMIA_DIR}/edutech"
FRONTEND_DIR="${ACADEMIA_DIR}/fahari-academia-front"

echo "=============================================="
echo " Starting Academia Deployment..."
echo "=============================================="

# 1. Pull latest code
echo ">>> Pulling latest code..."
cd "${BACKEND_DIR}"
if [ -d ".git" ]; then
    git pull origin "$(git rev-parse --abbrev-ref HEAD)" || true
fi

cd "${FRONTEND_DIR}"
if [ -d ".git" ]; then
    git pull origin "$(git rev-parse --abbrev-ref HEAD)" || true
fi

# 2. Dependency updates
echo ">>> Updating backend dependencies..."
cd "${BACKEND_DIR}"
if [ -d "venv" ]; then
    venv/bin/pip install --no-input -r requirements.txt
    venv/bin/pip install --no-input gunicorn
fi

echo ">>> Updating frontend dependencies..."
cd "${FRONTEND_DIR}"
npm install --no-audit --prefer-offline || npm install

# 3. Database migrations
echo ">>> Running Django tenant migrations..."
cd "${BACKEND_DIR}"
export DJANGO_SETTINGS_MODULE="config.settings.production"
venv/bin/python manage.py migrate_schemas --noinput

# 4. Frontend build
echo ">>> Building frontend..."
cd "${FRONTEND_DIR}"
npm run build

# 5. Static files collection
echo ">>> Collecting backend static files..."
cd "${BACKEND_DIR}"
venv/bin/python manage.py collectstatic --noinput

# 6. Normalize permissions
echo ">>> Setting permissions for www-data..."
chown -R www-data:www-data "${BACKEND_DIR}/media" "${BACKEND_DIR}/staticfiles" "${FRONTEND_DIR}/dist"
chmod -R 775 "${BACKEND_DIR}/media" "${BACKEND_DIR}/staticfiles" "${FRONTEND_DIR}/dist"

# 7. Service restart
echo ">>> Restarting services..."
systemctl restart gunicorn_academia
if systemctl list-unit-files | grep -q "celery_academia.service"; then
    systemctl restart celery_academia || true
fi

# 8. Reload Nginx
nginx -t && systemctl reload nginx

# 9. Clear Redis cache
if command -v redis-cli &> /dev/null; then
    echo ">>> Clearing Redis cache..."
    redis-cli flushall || true
fi

echo "=============================================="
echo " Deployment Complete!"
echo "=============================================="
