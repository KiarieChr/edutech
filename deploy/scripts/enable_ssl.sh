#!/bin/bash

# enable_ssl.sh
# This script applies the Let's Encrypt wildcard certificates to Nginx
# Run this AFTER certbot successfully issues your wildcard certificates.

DOMAIN="api.royalsoftwares.co.ke"
FRONTEND_DOMAIN="academia.royalsoftwares.co.ke"
BACKEND_DIR="/var/www/academia/edutech"
FRONTEND_DIR="/var/www/academia/fahari-academia-front"

# Check if cert exists
CERT_PATH="/etc/letsencrypt/live/royalsoftwares.co.ke/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/royalsoftwares.co.ke/privkey.pem"

if [ ! -f "$CERT_PATH" ]; then
    echo "ERROR: Certificate not found at $CERT_PATH"
    echo "Make sure Certbot successfully issued the certificate."
    exit 1
fi

echo ">>> Applying SSL to Nginx Configuration..."

cat <<EOF > /etc/nginx/sites-available/academia
# HTTP to HTTPS Redirects
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN} ${FRONTEND_DOMAIN} royalsoftwares.co.ke *.royalsoftwares.co.ke;
    return 301 https://\$host\$request_uri;
}

# Backend API Server
server {
    listen 443 ssl http2;
    server_name ${DOMAIN} www.${DOMAIN};

    ssl_certificate ${CERT_PATH};
    ssl_certificate_key ${KEY_PATH};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

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

# Frontend SPA Server
server {
    listen 443 ssl http2;
    server_name ${FRONTEND_DOMAIN} royalsoftwares.co.ke *.royalsoftwares.co.ke;

    ssl_certificate ${CERT_PATH};
    ssl_certificate_key ${KEY_PATH};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    root ${FRONTEND_DIR}/dist;
    index index.html;

    # Proxy API requests to backend
    location /api/ {
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_pass http://127.0.0.1:8000/api/;
    }

    location /static/ {
        alias ${BACKEND_DIR}/staticfiles/;
    }
    
    location /media/ {
        alias ${BACKEND_DIR}/media/;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

nginx -t && systemctl restart nginx
echo ">>> Nginx restarted with SSL enabled!"
