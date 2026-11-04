#!/usr/bin/env bash
# ==============================================================================
# deploy.sh
# Automated deployment script for Academia on Linux production.
# Handles git syncing, merge conflicts, unrelated histories, database backup,
# migrations, frontend build, permissions, and service restarts.
# ==============================================================================

set -euo pipefail

ACADEMIA_DIR="/var/www/academia"
BACKEND_DIR="${ACADEMIA_DIR}/edutech"
FRONTEND_DIR="${ACADEMIA_DIR}/fahari-academia-front"

# Always enforce production Django settings before any DB or Django command
export DJANGO_SETTINGS_MODULE="config.settings.production"

# Source production environment variables if .env exists
if [ -f "${BACKEND_DIR}/.env" ]; then
    set -a
    source "${BACKEND_DIR}/.env"
    set +a
fi

# Ensure PostgreSQL credentials are in the environment for pg_dump/psql
if [ -n "${DB_PASSWORD:-}" ]; then
    export PGPASSWORD="${DB_PASSWORD}"
elif [ -n "${POSTGRES_PASSWORD:-}" ]; then
    export PGPASSWORD="${POSTGRES_PASSWORD}"
fi

echo "=============================================="
echo " Starting Academia Deployment..."
echo " Environment: ${DJANGO_SETTINGS_MODULE}"
echo "=============================================="

# Helper function to reliably sync git repositories without halting on conflicts or unrelated histories
sync_repository() {
    local REPO_DIR="$1"
    local REPO_LABEL="$2"
    local DEFAULT_BRANCH="$3"

    echo ">>> Syncing ${REPO_LABEL} in ${REPO_DIR}..."
    if [ ! -d "${REPO_DIR}/.git" ]; then
        echo "Notice: ${REPO_DIR} is not a git repository. Skipping git pull."
        return 0
    fi

    cd "${REPO_DIR}"

    # Stash any local uncommitted tracked changes so git operations succeed
    git stash || true

    # Determine local active branch
    local LOCAL_BRANCH
    LOCAL_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "${DEFAULT_BRANCH}")

    # Fetch all branches from origin
    echo "Fetching origin for ${REPO_LABEL}..."
    git fetch origin --prune || true

    # Determine remote branch: prefer LOCAL_BRANCH, else DEFAULT_BRANCH, else main, else master
    local TARGET_BRANCH="${LOCAL_BRANCH}"
    if ! git rev-parse --verify "origin/${TARGET_BRANCH}" &>/dev/null; then
        if git rev-parse --verify "origin/${DEFAULT_BRANCH}" &>/dev/null; then
            TARGET_BRANCH="${DEFAULT_BRANCH}"
        elif git rev-parse --verify "origin/main" &>/dev/null; then
            TARGET_BRANCH="main"
        elif git rev-parse --verify "origin/master" &>/dev/null; then
            TARGET_BRANCH="master"
        fi
    fi

    echo "Merging origin/${TARGET_BRANCH} into ${LOCAL_BRANCH} (allowing unrelated histories & auto-resolving conflicts)..."
    if git merge "origin/${TARGET_BRANCH}" --allow-unrelated-histories -X theirs --no-edit; then
        echo "Successfully merged origin/${TARGET_BRANCH} for ${REPO_LABEL}."
    else
        echo "Notice: Merge conflict or divergence detected. Resetting to remote origin/${TARGET_BRANCH}..."
        git reset --hard "origin/${TARGET_BRANCH}"
    fi
}

# 1. Pre-deployment Database Backup
echo ">>> Taking pre-deployment database backup..."
cd "${BACKEND_DIR}"
if [ -d "venv" ]; then
    source venv/bin/activate
    if [ -f "scripts/db_backup.py" ]; then
        python scripts/db_backup.py || echo "Warning: Pre-deployment backup failed. Proceeding with caution..."
    fi
fi

# 2. Pull latest code with conflict & unrelated history handling
sync_repository "${BACKEND_DIR}" "Backend (edutech)" "main"
sync_repository "${FRONTEND_DIR}" "Frontend (fahari-academia-front)" "main"

# 3. Dependency updates
echo ">>> Updating backend dependencies..."
cd "${BACKEND_DIR}"
if [ -d "venv" ]; then
    venv/bin/pip install --no-input -r requirements.txt
    venv/bin/pip install --no-input gunicorn
fi

echo ">>> Updating frontend dependencies..."
cd "${FRONTEND_DIR}"
if [ -f "package.json" ]; then
    npm install --no-audit --prefer-offline || npm install
fi

# 4. Database migrations
echo ">>> Running Django tenant migrations (migrate_schemas)..."
cd "${BACKEND_DIR}"
venv/bin/python manage.py migrate_schemas --noinput

# 5. Frontend build
echo ">>> Building frontend (npm run build)..."
cd "${FRONTEND_DIR}"
npm run build

# 6. Static files collection
echo ">>> Collecting backend static files..."
cd "${BACKEND_DIR}"
venv/bin/python manage.py collectstatic --noinput

# 7. Normalize permissions
echo ">>> Setting permissions for www-data..."
chown -R www-data:www-data "${BACKEND_DIR}/media" "${BACKEND_DIR}/staticfiles" "${FRONTEND_DIR}/dist"
chmod -R 775 "${BACKEND_DIR}/media" "${BACKEND_DIR}/staticfiles" "${FRONTEND_DIR}/dist"

# 8. Service restart
echo ">>> Restarting services..."
systemctl restart gunicorn_academia
if systemctl list-unit-files | grep -q "celery_academia.service"; then
    systemctl restart celery_academia || true
fi

# 9. Reload Nginx
nginx -t && systemctl reload nginx

# 10. Clear Redis cache
if command -v redis-cli &> /dev/null; then
    echo ">>> Clearing Redis cache..."
    redis-cli flushall || true
fi

echo "=============================================="
echo " Deployment Complete!"
echo "=============================================="
