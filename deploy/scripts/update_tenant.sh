#!/bin/bash
# update_tenant.sh
# Run specific commands or migrations on a single tenant schema

set -e

BACKEND_DIR="/var/www/academia/edutech"

if [ -z "$1" ]; then
    echo "Usage: ./update_tenant.sh <schema_name> [command]"
    echo "Example (Migrate): ./update_tenant.sh client_abc"
    echo "Example (Custom): ./update_tenant.sh client_abc createsuperuser"
    exit 1
fi

SCHEMA_NAME="$1"
COMMAND="${2:-migrate}"

cd ${BACKEND_DIR}
source venv/bin/activate
export DJANGO_SETTINGS_MODULE="config.settings.production"

echo ">>> Running '$COMMAND' on tenant schema '$SCHEMA_NAME'..."
python manage.py tenant_command $COMMAND --schema=$SCHEMA_NAME

echo ">>> Tenant update complete."
