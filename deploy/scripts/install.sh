#!/usr/bin/env bash
# ==============================================================================
# Fahari Academia - Complete First-Time Linux Installation Script
# Operating System: Ubuntu 22.04 / 24.04 LTS or Debian 11/12
# Folder Structure Target:
#   /var/www/academia/edutech (Backend - Django + DRF)
#   /var/www/academia/fahari-academia-front (Frontend - React + Vite)
# ==============================================================================

set -euo pipefail

# Text styling
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

log_info() { echo -e "${BOLD}${GREEN}[INFO]${RESET} $1"; }
log_warn() { echo -e "${BOLD}${YELLOW}[WARN]${RESET} $1"; }
log_error() { echo -e "${BOLD}${RED}[ERROR]${RESET} $1"; }

# 1. Root / Sudo Check
if [ "$EUID" -ne 0 ]; then
    log_error "This installation script must be run as root or with sudo."
    echo "Usage: sudo bash install.sh"
    exit 1
fi

BASE_DIR="/var/www/academia"
BACKEND_DIR="${BASE_DIR}/edutech"
FRONTEND_DIR="${BASE_DIR}/fahari-academia-front"
LOGS_DIR="${BACKEND_DIR}/logs"
MEDIA_DIR="${BACKEND_DIR}/media"
STATIC_DIR="${BACKEND_DIR}/staticfiles"

log_info "Starting Fahari Academia First-Time Setup on Linux..."

# 2. Update System & Install Core Packages
log_info "Installing required Linux packages and PDF / WeasyPrint dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    curl wget git build-essential \
    python3 python3-venv python3-dev python3-pip \
    libpq-dev postgresql-client \
    nginx redis-server \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev \
    shared-mime-info libxml2-dev libxslt1-dev zlib1g-dev \
    supervisor

# Enable and start Redis
systemctl enable redis-server || systemctl enable redis
systemctl start redis-server || systemctl start redis || true

# 3. Install Node.js 20 LTS (if not present or version < 18)
if ! command -v node &> /dev/null || [ "$(node -v | cut -d'v' -f2 | cut -d'.' -f1)" -lt 18 ]; then
    log_info "Installing Node.js 20 LTS from NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
log_info "Node version: $(node -v) | NPM version: $(npm -v)"

# 4. Prepare Directory Structure
log_info "Preparing folder structure at ${BASE_DIR}..."
mkdir -p "${BASE_DIR}"
mkdir -p "${LOGS_DIR}" "${MEDIA_DIR}" "${STATIC_DIR}"

# 5. Clone or Verify Repositories
if [ ! -d "${BACKEND_DIR}/.git" ] && [ ! -f "${BACKEND_DIR}/manage.py" ]; then
    log_info "Cloning backend repository..."
    git clone https://github.com/KiarieChr/edutech.git "${BACKEND_DIR}"
fi

if [ ! -d "${FRONTEND_DIR}/.git" ] && [ ! -f "${FRONTEND_DIR}/package.json" ]; then
    log_info "Cloning frontend repository..."
    git clone https://github.com/KiarieChr/fahari-academia-front.git "${FRONTEND_DIR}"
fi

# 6. Backend Setup (Python venv, dependencies, migrations)
log_info "Setting up Python Virtual Environment in ${BACKEND_DIR}/venv..."
export DJANGO_SETTINGS_MODULE="config.settings.production"
cd "${BACKEND_DIR}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Ensure pip & setuptools are latest
venv/bin/python -m pip install --upgrade pip setuptools wheel
venv/bin/pip install -r requirements.txt
venv/bin/pip install gunicorn

# Ensure .env exists
if [ ! -f .env ]; then
    log_warn "Creating default .env for backend from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        cat <<EOT > .env
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,localhost,app.royalsoftwares.co.ke,academia.royalsoftwares.co.ke,.royalsoftwares.co.ke
DATABASE_NAME=edutechdb
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_HOST=localhost
DATABASE_PORT=5432
REDIS_URL=redis://127.0.0.1:6379/1
EOT
    fi
fi

# Run initial migrations and static collection
log_info "Running multi-tenant database migrations (migrate_schemas)..."
venv/bin/python manage.py migrate_schemas --noinput || {
    log_warn "Initial migrate_schemas exited with an error. Ensure PostgreSQL is running and DB credentials in .env are correct."
}

log_info "Collecting backend static files..."
venv/bin/python manage.py collectstatic --noinput

# 7. Frontend Setup (npm install & build)
log_info "Setting up Frontend at ${FRONTEND_DIR}..."
cd "${FRONTEND_DIR}"

if [ ! -f .env ]; then
    log_info "Writing production .env for frontend..."
    cat <<EOT > .env
VITE_API_URL=
VITE_TOKEN_KEY=academia-token
VITE_REFRESH_KEY=academia-refresh
VITE_USER_KEY=academia-user
EOT
fi

log_info "Installing frontend npm packages..."
npm install --no-audit --prefer-offline || npm install

log_info "Building frontend for production (Vite build)..."
npm run build

# 8. Configure Systemd Service for Gunicorn
log_info "Configuring /etc/systemd/system/gunicorn_academia.service..."
cat <<EOT > /etc/systemd/system/gunicorn_academia.service
[Unit]
Description=gunicorn daemon for Academia Backend
After=network.target redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=${BACKEND_DIR}
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=${BACKEND_DIR}/venv/bin/gunicorn -c ${BACKEND_DIR}/deploy/gunicorn.conf.py config.wsgi:application
Restart=always
RestartSec=3
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOT

systemctl daemon-reload
systemctl enable gunicorn_academia
systemctl restart gunicorn_academia

# 9. Configure Nginx
log_info "Configuring Nginx site: /etc/nginx/sites-available/academia..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/nginx.conf" ]; then
    cp "${SCRIPT_DIR}/nginx.conf" /etc/nginx/sites-available/academia
else
    log_warn "nginx.conf not found next to install.sh. Leaving existing site config in place."
fi

# Enable site
ln -sf /etc/nginx/sites-available/academia /etc/nginx/sites-enabled/academia
# Remove default site if present
rm -f /etc/nginx/sites-enabled/default

# 10. Fix Linux File Ownership & Permissions
log_info "Setting correct permissions for www-data..."
chown -R www-data:www-data "${BASE_DIR}"
chmod -R 755 "${BASE_DIR}"
chmod -R 775 "${MEDIA_DIR}" "${STATIC_DIR}" "${LOGS_DIR}" "${FRONTEND_DIR}/dist"

# 11. Test and Reload Nginx
log_info "Testing Nginx syntax..."
nginx -t
systemctl reload nginx

log_info "================================================================="
log_info " Fahari Academia Installation Successfully Completed!"
log_info " - Backend:  ${BACKEND_DIR}"
log_info " - Frontend: ${FRONTEND_DIR}/dist"
log_info " - Service:  gunicorn_academia.service"
log_info " - Nginx:    /etc/nginx/sites-available/academia"
log_info "================================================================="
