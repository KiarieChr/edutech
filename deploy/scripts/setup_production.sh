#!/bin/bash
# setup_production.sh
# Bare-metal provisioning script for Ubuntu/Debian server.
# Run with sudo.

set -e

# Configuration
ACADEMIA_DIR="/var/www/academia"
BACKEND_DIR="${ACADEMIA_DIR}/edutech"
FRONTEND_DIR="${ACADEMIA_DIR}/fahari-academia-front"
DB_NAME="edutechdb"
DB_USER="postgres"
DB_PASS="password" # CHANGE THIS IN PRODUCTION
DOMAIN="api.royalsoftwares.co.ke"
FRONTEND_DOMAIN="academia.royalsoftwares.co.ke"

echo "=============================================="
echo " Starting Production Setup for Academia"
echo "=============================================="

# 1. System package installation
echo ">>> Updating system packages..."
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx redis-server build-essential libpq-dev curl git certbot python3-certbot-nginx nodejs npm

# 2. PostgreSQL setup
echo ">>> Configuring PostgreSQL..."
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME};" || echo "Database already exists"
sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" || echo "User update failed or already configured"
sudo -u postgres psql -c "ALTER ROLE ${DB_USER} SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE ${DB_USER} SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE ${DB_USER} SET timezone TO 'UTC';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

# 3. Python virtual environment setup
echo ">>> Setting up Python virtual environment..."
cd ${BACKEND_DIR}
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
# Install packages one by one, ignoring failures
while read package; do
    if [ ! -z "$package" ]; then
        pip install "$package" || echo "WARNING: Failed to install $package, skipping..."
    fi
done < requirements.txt

# 4. Django migrations and static files
echo ">>> Running initial migrations and collecting static files..."
export DJANGO_SETTINGS_MODULE="config.settings.production"
python manage.py collectstatic --noinput
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant

# 5. Gunicorn service configuration (systemd)
echo ">>> Configuring Gunicorn systemd service..."
cat <<EOF > /etc/systemd/system/gunicorn_academia.service
[Unit]
Description=gunicorn daemon for Academia Backend
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=${BACKEND_DIR}
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=${BACKEND_DIR}/venv/bin/gunicorn -c ${BACKEND_DIR}/deploy/gunicorn.conf.py config.wsgi:application

[Install]
WantedBy=multi-user.target
EOF

# 6. Celery service configuration
echo ">>> Configuring Celery systemd service..."
cat <<EOF > /etc/systemd/system/celery_academia.service
[Unit]
Description=Celery Service for Academia Backend
After=network.target redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=${BACKEND_DIR}
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=${BACKEND_DIR}/venv/bin/celery -A config worker -l info

[Install]
WantedBy=multi-user.target
EOF

# 7. Reload systemd and start services
echo ">>> Starting backend services..."
systemctl daemon-reload
systemctl enable gunicorn_academia celery_academia redis-server
systemctl restart gunicorn_academia celery_academia redis-server

# 8. Nginx configuration with SSL
echo ">>> Configuring Nginx for Backend and Frontend..."
cat <<EOF > /etc/nginx/sites-available/academia
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        alias ${BACKEND_DIR}/staticfiles/;
    }
    
    location /media/ {
        alias ${BACKEND_DIR}/media/;
    }

    location / {
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_pass http://127.0.0.1:8000;
    }
}

server {
    listen 80;
    server_name ${FRONTEND_DOMAIN} *.${FRONTEND_DOMAIN};

    root ${FRONTEND_DIR}/dist;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/academia /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# 9. Let's Encrypt SSL setup
echo ">>> Requesting SSL certificate..."
# Note: Certbot will fail if DNS is not yet pointed to this server.
# Wildcard certificates (*.royalsoftwares.co.ke) require DNS-01 challenge.
# This script will attempt HTTP challenge for the base domains. You must run DNS challenge manually for wildcards.
certbot --nginx -d ${DOMAIN} -d www.${DOMAIN} -d ${FRONTEND_DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN} || echo "Certbot failed. Ensure DNS is configured."

# 10. Backup cron job setup
echo ">>> Configuring automated backups..."
(crontab -l 2>/dev/null; echo "0 2 * * * ${BACKEND_DIR}/venv/bin/python ${BACKEND_DIR}/scripts/db_backup.py >> ${BACKEND_DIR}/logs/cron_backup.log 2>&1") | crontab -

echo "=============================================="
echo " Setup Complete! Verify service status with:"
echo " systemctl status gunicorn_academia celery_academia nginx"
echo "=============================================="
