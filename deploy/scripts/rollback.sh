#!/bin/bash
# rollback.sh
# Emergency rollback script to revert code and database.

set -e

BACKEND_DIR="/var/www/academia/edutech"
FRONTEND_DIR="/var/www/academia/fahari-academia-front"

echo "=============================================="
echo " EMERGENCY ROLLBACK INITIATED"
echo "=============================================="
echo "WARNING: This will revert your code to the previous Git commit and prompt a database restore."
read -p "Type 'ROLLBACK' to confirm: " confirm
if [ "$confirm" != "ROLLBACK" ]; then
    echo "Aborted."
    exit 0
fi

# 1. Revert Backend Code
echo ">>> Reverting backend code to previous commit (HEAD^1)..."
cd ${BACKEND_DIR}
git reset --hard HEAD^1

# 2. Revert Frontend Code
echo ">>> Reverting frontend code to previous commit (HEAD^1)..."
cd ${FRONTEND_DIR}
git reset --hard HEAD^1
npm install
npm run build

# 3. Database Restore
echo ">>> Initiating database restore interface..."
cd ${BACKEND_DIR}
source venv/bin/activate
export DJANGO_SETTINGS_MODULE="config.settings.production"
python scripts/db_restore.py

# 4. Cleanup
echo ">>> Collecting static files..."
python manage.py collectstatic --noinput

echo ">>> Restarting services..."
sudo systemctl restart gunicorn_academia
sudo systemctl restart celery_academia

echo ">>> Clearing Redis cache..."
redis-cli flushall

echo "=============================================="
echo " Rollback Complete!"
echo "=============================================="
