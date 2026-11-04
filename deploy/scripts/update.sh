#!/usr/bin/env bash
# ==============================================================================
# Fahari Academia - Production Update Script
# Updates backend code, runs schema migrations, collects static files,
# builds React frontend, fixes permissions, and restarts services with health check.
#
# Usage:
#   sudo bash update.sh               # Standard update (git pull + build + reload)
#   sudo bash update.sh --no-pull      # Skip git pull (for local/manual uploads)
# ==============================================================================

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

log_info()  { echo -e "${BOLD}${GREEN}[INFO]${RESET} $1"; }
log_warn()  { echo -e "${BOLD}${YELLOW}[WARN]${RESET} $1"; }
log_error() { echo -e "${BOLD}${RED}[ERROR]${RESET} $1"; }

if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root or with sudo."
    echo "Usage: sudo bash update.sh"
    exit 1
fi

BASE_DIR="/var/www/academia"
BACKEND_DIR="${BASE_DIR}/edutech"
FRONTEND_DIR="${BASE_DIR}/fahari-academia-front"
LOGS_DIR="${BACKEND_DIR}/logs"
MEDIA_DIR="${BACKEND_DIR}/media"
STATIC_DIR="${BACKEND_DIR}/staticfiles"

# Always enforce production Django settings
export DJANGO_SETTINGS_MODULE="config.settings.production"

# Source production environment variables if .env exists
if [ -f "${BACKEND_DIR}/.env" ]; then
    set -a
    source "${BACKEND_DIR}/.env"
    set +a
fi

# Ensure PostgreSQL credentials and port are in the environment for pg_dump/psql
if [ -n "${DB_PASSWORD:-}" ]; then
    export PGPASSWORD="${DB_PASSWORD}"
elif [ -n "${POSTGRES_PASSWORD:-}" ]; then
    export PGPASSWORD="${POSTGRES_PASSWORD}"
fi
export PGPORT="${DB_PORT:-5433}"
export PGHOST="${DB_HOST:-localhost}"

DO_PULL=true
if [[ "${*:-}" == *"--no-pull"* ]]; then
    DO_PULL=false
fi

log_info "================================================================="
log_info " Starting Fahari Academia Application Update..."
log_info " Working Directory: ${BASE_DIR}"
log_info " Environment:       ${DJANGO_SETTINGS_MODULE}"
log_info "================================================================="

# Helper function to reliably sync git repositories without halting on conflicts or unrelated histories
sync_repository() {
    local REPO_DIR="$1"
    local REPO_LABEL="$2"
    local DEFAULT_BRANCH="$3"

    log_info ">>> Syncing ${REPO_LABEL} in ${REPO_DIR}..."
    if [ ! -d "${REPO_DIR}/.git" ]; then
        log_warn "${REPO_DIR} is not a git repository. Skipping git pull."
        return 0
    fi

    cd "${REPO_DIR}"
    git stash || true

    local LOCAL_BRANCH
    LOCAL_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "${DEFAULT_BRANCH}")

    git fetch origin --prune || true

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

    log_info "Merging origin/${TARGET_BRANCH} into ${LOCAL_BRANCH} (allowing unrelated histories & auto-resolving conflicts)..."
    if git merge "origin/${TARGET_BRANCH}" --allow-unrelated-histories -X theirs --no-edit; then
        log_info "Successfully merged origin/${TARGET_BRANCH} for ${REPO_LABEL}."
    else
        log_warn "Merge conflict or divergence detected. Resetting to remote origin/${TARGET_BRANCH}..."
        git reset --hard "origin/${TARGET_BRANCH}"
    fi
}

# Helper function to ensure venv uses a modern Python version (>= 3.10)
ensure_modern_venv() {
    cd "${BACKEND_DIR}"
    local NEED_REBUILD=false

    if [ ! -d "venv" ] || [ ! -f "venv/bin/python" ]; then
        NEED_REBUILD=true
    else
        local VENV_PY_VER
        VENV_PY_VER=$(venv/bin/python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        local VENV_MAJOR=$(echo "$VENV_PY_VER" | cut -d'.' -f1)
        local VENV_MINOR=$(echo "$VENV_PY_VER" | cut -d'.' -f2)
        if [ "$VENV_MAJOR" -lt 3 ] || [ "$VENV_MINOR" -lt 10 ]; then
            log_warn "Detected Python ${VENV_PY_VER} in venv (< 3.10). Modern Python is required for tinyhtml5/weasyprint."
            NEED_REBUILD=true
        fi
    fi

    if [ "$NEED_REBUILD" = true ]; then
        local CHOSEN_PY=""
        for cand in python3.12 python3.11 python3.14 python3.10 python3; do
            if command -v "$cand" &>/dev/null; then
                local PY_VER
                PY_VER=$("$cand" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
                local MAJ=$(echo "$PY_VER" | cut -d'.' -f1)
                local MIN=$(echo "$PY_VER" | cut -d'.' -f2)
                if [ "$MAJ" -eq 3 ] && [ "$MIN" -ge 10 ]; then
                    CHOSEN_PY="$cand"
                    break
                fi
            fi
        done

        if [ -z "$CHOSEN_PY" ]; then
            log_error "No Python >= 3.10 found. Please install python3.11 or python3.12 on the server."
            return 1
        fi

        log_info ">>> Building new virtual environment with ${CHOSEN_PY} ($($CHOSEN_PY --version))..."
        if [ -d "venv" ]; then
            rm -rf venv_py38_backup 2>/dev/null || true
            mv venv venv_py38_backup
        fi
        "$CHOSEN_PY" -m venv venv
        venv/bin/python -m pip install --upgrade pip setuptools wheel
    fi
}

# 1. Pull Latest Changes from Git
if [ "$DO_PULL" = true ]; then
    sync_repository "${BACKEND_DIR}" "Backend (edutech)" "main"
    sync_repository "${FRONTEND_DIR}" "Frontend (fahari-academia-front)" "main"
else
    log_info ">>> Skipping git pull as requested (--no-pull)."
fi

# 2. Ensure modern Python virtualenv (>= 3.10)
ensure_modern_venv

# 3. Pre-deployment Database Backup
log_info ">>> Taking pre-deployment database backup..."
cd "${BACKEND_DIR}"
if [ -d "venv" ] && [ -f "scripts/db_backup.py" ]; then
    venv/bin/python scripts/db_backup.py || log_warn "Pre-deployment backup had a warning. Proceeding..."
fi

# 4. Update Backend Python Dependencies
log_info ">>> Checking Python dependencies..."
cd "${BACKEND_DIR}"
venv/bin/pip install --no-input -r requirements.txt
venv/bin/pip install --no-input gunicorn

# 4. Database Schema Migrations (Tenant-aware)
log_info ">>> Running Django schema migrations (migrate_schemas)..."
cd "${BACKEND_DIR}"
venv/bin/python manage.py migrate_schemas --noinput

# 5. Collect Backend Static Files
log_info ">>> Collecting static files..."
venv/bin/python manage.py collectstatic --noinput

# 6. Build React Frontend
log_info ">>> Installing frontend npm packages & building production bundle..."
cd "${FRONTEND_DIR}"
if [ -f "package.json" ]; then
    npm install --no-audit --prefer-offline || npm install
    npm run build
fi

# 7. Update Nginx Configuration (if updated template exists)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/nginx.conf" ]; then
    log_info ">>> Updating /etc/nginx/sites-available/academia..."
    cp "${SCRIPT_DIR}/nginx.conf" /etc/nginx/sites-available/academia
    ln -sf /etc/nginx/sites-available/academia /etc/nginx/sites-enabled/academia
fi

# 8. Set Permissions
log_info ">>> Normalizing directory permissions for www-data..."
mkdir -p "${LOGS_DIR}" "${MEDIA_DIR}" "${STATIC_DIR}"
chown -R www-data:www-data "${MEDIA_DIR}" "${STATIC_DIR}" "${LOGS_DIR}" "${FRONTEND_DIR}/dist"
chmod -R 775 "${MEDIA_DIR}" "${STATIC_DIR}" "${LOGS_DIR}" "${FRONTEND_DIR}/dist"

# 9. Clear Redis Cache (optional if redis-cli available)
if command -v redis-cli &> /dev/null; then
    log_info ">>> Flushing Redis cache..."
    redis-cli flushall || log_warn "Redis flushall skipped or failed."
fi

# 10. Test Nginx and Restart Services
log_info ">>> Testing Nginx configuration..."
nginx -t

log_info ">>> Reloading Nginx..."
systemctl reload nginx

log_info ">>> Restarting Gunicorn Backend service..."
systemctl restart gunicorn_academia

if systemctl list-unit-files | grep -q "celery_academia.service"; then
    log_info ">>> Restarting Celery service..."
    systemctl restart celery_academia || true
fi

# 11. Automated Health Check
log_info ">>> Running post-update health check..."
sleep 2

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/ || echo "000")
if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 500 ]; then
    log_info "Backend Health Check: OK (HTTP ${HTTP_STATUS})"
else
    log_warn "Backend returned HTTP ${HTTP_STATUS}. Check journalctl -u gunicorn_academia -n 50"
fi

if [ -f "${FRONTEND_DIR}/dist/index.html" ]; then
    log_info "Frontend Build: Verified (${FRONTEND_DIR}/dist/index.html present)"
else
    log_error "Frontend dist/index.html not found! Build may have failed."
fi

log_info "================================================================="
log_info " Fahari Academia Update Successfully Completed!"
log_info "================================================================="
