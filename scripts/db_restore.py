#!/usr/bin/env python
import os
import sys
import subprocess
import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(r"C:\backup\projects\edutech")
BACKUP_DIR = BASE_DIR / "backups"

def bootstrap_django():
    """Bootstrap Django to use its ORM and configuration."""
    sys.path.insert(0, str(BASE_DIR))
    sys.path.insert(0, str(BASE_DIR / 'apps'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    import django
    django.setup()
    from django.conf import settings
    return settings


def get_db_config(settings):
    """Extract DB credentials from Django settings."""
    db = settings.DATABASES['default']
    return {
        'host': db.get('HOST', 'localhost'),
        'port': str(db.get('PORT', '5432')),
        'user': db['USER'],
        'password': db['PASSWORD'],
        'name': db['NAME']
    }

def list_backups():
    """List available backups."""
    if not BACKUP_DIR.exists():
        logger.error(f"Backup directory {BACKUP_DIR} does not exist.")
        return []
        
    backups = []
    for f in BACKUP_DIR.iterdir():
        if f.name.endswith(".dump"):
            size_mb = f.stat().st_size / (1024 * 1024)
            mtime = f.stat().st_mtime
            backups.append((f, size_mb, mtime))
            
    backups.sort(key=lambda x: x[2], reverse=True) # Sort newest first
    
    print("\n--- Available Backups ---")
    for idx, (f, size, _) in enumerate(backups):
        print(f"[{idx}] {f.name} ({size:.2f} MB)")
        
    return backups

def drop_and_recreate_db(db_config):
    """Terminate connections, drop, and recreate the database."""
    logger.info("Connecting to default postgres database to drop target DB...")
    
    try:
        # Connect to 'postgres' db to drop the target DB
        conn = psycopg2.connect(
            dbname='postgres',
            user=db_config['user'],
            password=db_config['password'],
            host=db_config['host'],
            port=db_config['port']
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        target_db = db_config['name']
        
        logger.info(f"Terminating active connections to {target_db}...")
        cursor.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{target_db}'
            AND pid <> pg_backend_pid();
        """)
        
        logger.info(f"Dropping database {target_db}...")
        cursor.execute(f"DROP DATABASE IF EXISTS {target_db};")
        
        logger.info(f"Recreating database {target_db}...")
        cursor.execute(f"CREATE DATABASE {target_db};")
        
        cursor.close()
        conn.close()
        logger.info("Database recreated successfully.")
        
    except Exception as e:
        logger.error(f"Failed to drop/recreate database: {e}")
        sys.exit(1)

def run_pg_restore(db_config, dump_file):
    """Restore the database using pg_restore."""
    env = os.environ.copy()
    env['PGPASSWORD'] = db_config['password']
    
    pg_restore_cmd = [
        "pg_restore",
        "-h", db_config['host'],
        "-p", db_config['port'],
        "-U", db_config['user'],
        "-d", db_config['name'],
        "-1", # Run as a single transaction
        str(dump_file)
    ]
    
    logger.info(f"Starting pg_restore from {dump_file.name}...")
    try:
        # Note: pg_restore often outputs warnings to stderr even on success
        result = subprocess.run(pg_restore_cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.warning("pg_restore completed with warnings/errors:")
            logger.warning(result.stderr)
        else:
            logger.info("Restore completed successfully.")
            
    except Exception as e:
        logger.error(f"Restore failed completely: {e}")
        sys.exit(1)

def post_restore_tasks():
    """Clear caches or run migrations."""
    logger.info("Running post-restore tasks...")
    try:
        from django.core.cache import cache
        cache.clear()
        logger.info("Redis cache cleared.")
    except Exception as e:
        logger.warning(f"Failed to clear cache: {e}")

def main():
    settings = bootstrap_django()
    db_config = get_db_config(settings)
    
    backups = list_backups()
    if not backups:
        print("No backups found to restore.")
        sys.exit(1)
        
    try:
        selection = input("\nEnter the number of the backup to restore (or 'q' to quit): ")
        if selection.lower() == 'q':
            sys.exit(0)
            
        idx = int(selection)
        target_backup = backups[idx][0]
    except (ValueError, IndexError):
        print("Invalid selection.")
        sys.exit(1)
        
    print(f"\nWARNING: You are about to completely overwrite the '{db_config['name']}' database with '{target_backup.name}'.")
    confirm = input("Type 'RESTORE' to confirm: ")
    
    if confirm != 'RESTORE':
        print("Aborted.")
        sys.exit(0)
        
    # Execution
    drop_and_recreate_db(db_config)
    run_pg_restore(db_config, target_backup)
    post_restore_tasks()
    
    logger.info("Process complete.")

if __name__ == "__main__":
    main()
