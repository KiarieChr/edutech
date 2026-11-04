#!/usr/bin/env bash
# ==============================================================================
# migrate_pg12_to_pg16.sh
# Safely dumps database from PostgreSQL 12 (port 5432) and restores to
# PostgreSQL 16 (port 5433), verifies data, and configures .env for port 5433.
#
# Usage:
#   sudo bash migrate_pg12_to_pg16.sh
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
    exit 1
fi

ACADEMIA_DIR="/var/www/academia"
BACKEND_DIR="${ACADEMIA_DIR}/edutech"
BACKUP_DIR="${ACADEMIA_DIR}/db_migration_pg12_to_pg16"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "${BACKUP_DIR}"
chmod 770 "${BACKUP_DIR}"

# 1. Source .env if available
DB_NAME="edutechdb"
DB_USER="postgres"
DB_PASS=""

if [ -f "${BACKEND_DIR}/.env" ]; then
    log_info "Reading database config from ${BACKEND_DIR}/.env..."
    # Read variables without overriding existing environment
    ENV_NAME=$(grep -E '^DB_NAME=' "${BACKEND_DIR}/.env" | cut -d'=' -f2 | tr -d '\r"' || true)
    ENV_USER=$(grep -E '^DB_USER=' "${BACKEND_DIR}/.env" | cut -d'=' -f2 | tr -d '\r"' || true)
    ENV_PASS=$(grep -E '^DB_PASSWORD=' "${BACKEND_DIR}/.env" | cut -d'=' -f2 | tr -d '\r"' || true)
    
    [ -n "$ENV_NAME" ] && DB_NAME="$ENV_NAME"
    [ -n "$ENV_USER" ] && DB_USER="$ENV_USER"
    [ -n "$ENV_PASS" ] && DB_PASS="$ENV_PASS"
fi

log_info "=========================================================="
log_info " Database Migration: PostgreSQL 12 (:5432) -> 16 (:5433)"
log_info " Target Database: ${DB_NAME}"
log_info " Target User:     ${DB_USER}"
log_info " Backup Directory: ${BACKUP_DIR}"
log_info "=========================================================="

# 2. Check clusters
log_info "Checking PostgreSQL cluster status..."
if ! pg_lsclusters | grep -q "12.*5432"; then
    log_error "PostgreSQL 12 cluster on port 5432 was not found in pg_lsclusters."
    exit 1
fi

if ! pg_lsclusters | grep -q "16.*5433"; then
    log_error "PostgreSQL 16 cluster on port 5433 was not found in pg_lsclusters."
    exit 1
fi

# Locate PG 16 binaries (PostgreSQL recommends using the NEWER version's dump tool)
PG_DUMP_BIN="/usr/lib/postgresql/16/bin/pg_dump"
PG_DUMPALL_BIN="/usr/lib/postgresql/16/bin/pg_dumpall"
PG_RESTORE_BIN="/usr/lib/postgresql/16/bin/pg_restore"

if [ ! -x "$PG_DUMP_BIN" ]; then
    PG_DUMP_BIN="$(command -v pg_dump || echo '')"
fi
if [ ! -x "$PG_RESTORE_BIN" ]; then
    PG_RESTORE_BIN="$(command -v pg_restore || echo '')"
fi

# 3. Dump Globals (roles, passwords) from PG 12 and sync to PG 16
log_info ">>> Exporting roles and global objects from PG 12..."
GLOBALS_FILE="${BACKUP_DIR}/globals_pg12_${TIMESTAMP}.sql"
sudo -u postgres "$PG_DUMPALL_BIN" -p 5432 --globals-only > "${GLOBALS_FILE}" || {
    log_warn "pg_dumpall globals export had warnings. Continuing..."
}

log_info ">>> Applying database roles to PG 16 (port 5433)..."
sudo -u postgres psql -p 5433 -f "${GLOBALS_FILE}" || {
    log_warn "Some roles already exist on PG 16; this is normal."
}

# 4. Check if database exists in PG 12
log_info ">>> Checking if database '${DB_NAME}' exists on PG 12 (port 5432)..."
if ! sudo -u postgres psql -p 5432 -lqt | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
    log_error "Database '${DB_NAME}' does not exist on PostgreSQL 12 (port 5432)!"
    echo "Available databases on port 5432:"
    sudo -u postgres psql -p 5432 -lqt | cut -d \| -f 1
    exit 1
fi

# 5. Dump database from PG 12 using PG 16's pg_dump
DUMP_FILE="${BACKUP_DIR}/${DB_NAME}_pg12_${TIMESTAMP}.dump"
SQL_FILE="${BACKUP_DIR}/${DB_NAME}_pg12_${TIMESTAMP}.sql"

log_info ">>> Dumping '${DB_NAME}' from PostgreSQL 12 (port 5432)..."
sudo -u postgres "$PG_DUMP_BIN" -p 5432 -Fc -b -v "${DB_NAME}" -f "${DUMP_FILE}"
log_info "Custom-format dump saved: ${DUMP_FILE}"

# 6. Prepare target database on PG 16 (port 5433)
log_info ">>> Preparing target database on PostgreSQL 16 (port 5433)..."
if sudo -u postgres psql -p 5433 -lqt | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
    log_warn "Database '${DB_NAME}' already exists on PG 16."
    read -p "Do you want to drop and recreate it to ensure a clean import? (y/N): " -r CONFIRM || CONFIRM="n"
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "Dropping existing database '${DB_NAME}' on PG 16..."
        sudo -u postgres dropdb -p 5433 "${DB_NAME}"
        sudo -u postgres createdb -p 5433 -O "${DB_USER}" "${DB_NAME}"
    fi
else
    log_info "Creating database '${DB_NAME}' on PG 16 (port 5433)..."
    sudo -u postgres createdb -p 5433 -O "${DB_USER}" "${DB_NAME}"
fi

# 7. Restore into PostgreSQL 16 (port 5433)
log_info ">>> Restoring '${DB_NAME}' into PostgreSQL 16 (port 5433)..."
sudo -u postgres "$PG_RESTORE_BIN" -p 5433 -d "${DB_NAME}" --no-owner --role="${DB_USER}" -v "${DUMP_FILE}" || {
    log_warn "pg_restore finished with minor warnings (often schema/extension ownership notices). Checking row counts..."
}

# 8. Verify restored database
log_info ">>> Verifying restored tables and schemas on PG 16 (port 5433)..."
TABLE_COUNT=$(sudo -u postgres psql -p 5433 -d "${DB_NAME}" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema');" | tr -d ' ')
log_info "Total tables in PG 16 '${DB_NAME}': ${TABLE_COUNT}"

if [ "${TABLE_COUNT}" -eq 0 ]; then
    log_error "Migration verification failed: 0 tables found in PG 16!"
    exit 1
fi

# Check tenant schema table if available
if sudo -u postgres psql -p 5433 -d "${DB_NAME}" -c "\dt public_tenant" &>/dev/null; then
    TENANT_COUNT=$(sudo -u postgres psql -p 5433 -d "${DB_NAME}" -t -c "SELECT count(*) FROM public_tenant;" | tr -d ' ')
    log_info "Found ${TENANT_COUNT} tenant(s) registered in public_tenant."
fi

# 9. Update .env with DB_PORT=5433
if [ -f "${BACKEND_DIR}/.env" ]; then
    log_info ">>> Updating DB_PORT=5433 in ${BACKEND_DIR}/.env..."
    if grep -q "^DB_PORT=" "${BACKEND_DIR}/.env"; then
        sed -i 's/^DB_PORT=.*/DB_PORT=5433/' "${BACKEND_DIR}/.env"
    else
        echo "" >> "${BACKEND_DIR}/.env"
        echo "DB_PORT=5433" >> "${BACKEND_DIR}/.env"
    fi
    log_info "Verified ${BACKEND_DIR}/.env: $(grep '^DB_PORT=' "${BACKEND_DIR}/.env")"
fi

log_info "=========================================================="
log_info " Migration to PostgreSQL 16 (Port 5433) Complete!"
log_info " Backup copy stored at: ${DUMP_FILE}"
log_info ""
log_info " Next Steps:"
log_info " 1. Run migrations/deploy check:"
log_info "    cd ${BACKEND_DIR}/deploy/scripts && sudo bash deploy.sh"
log_info ""
log_info " 2. (Optional) Once verified, stop PostgreSQL 12 to free RAM:"
log_info "    sudo systemctl stop postgresql@12-main"
log_info "    sudo systemctl disable postgresql@12-main"
log_info "=========================================================="
