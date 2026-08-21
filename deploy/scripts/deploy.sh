#!/bin/bash
# deploy.sh
# Routine CI/CD deployment script for Academia.

set -e

ACADEMIA_DIR="/var/www/academia"
BACKEND_DIR="${ACADEMIA_DIR}/edutech"
FRONTEND_DIR="${ACADEMIA_DIR}/fahari-academia-front"

echo "=============================================="
echo " Starting Deployment..."
echo "=============================================="

# 1. Pre-deployment backup
echo ">>> Taking pre-deployment database backup..."
cd ${BACKEND_DIR}
source venv/bin/activate
python scripts/db_backup.py || echo "Warning: Backup failed. Proceeding with caution..."

# 2. Git pull latest changes
echo ">>> Pulling latest code..."
cd ${BACKEND_DIR}
git pull origin main
cd ${FRONTEND_DIR}
git pull origin main

# 3. Dependency updates
echo ">>> Updating backend dependencies..."
cd ${BACKEND_DIR}
pip install -r requirements.txt

echo ">>> Updating frontend dependencies..."
cd ${FRONTEND_DIR}
npm install

# 4. Database migrations
echo ">>> Running Django migrations..."
cd ${BACKEND_DIR}
export DJANGO_SETTINGS_MODULE="config.settings.production"
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant

# 5. Frontend build
echo ">>> Building frontend..."
cd ${FRONTEND_DIR}
npm run build

# 6. Static files collection
echo ">>> Collecting backend static files..."
cd ${BACKEND_DIR}
python manage.py collectstatic --noinput

# 7. Service restart
echo ">>> Restarting services..."
sudo systemctl restart gunicorn_academia
sudo systemctl restart celery_academia

# 8. Cache clearing
echo ">>> Clearing Redis cache..."
redis-cli flushall

# 9. Health check
echo ">>> Verifying deployment..."
curl -I https://api.royalsoftwares.co.ke || echo "Backend check failed!"
curl -I https://fahari.royalsoftwares.co.ke || echo "Frontend check failed!"

echo "=============================================="
echo " Deployment Complete!"
echo "=============================================="
