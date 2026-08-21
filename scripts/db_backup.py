#!/usr/bin/env python
import os
import sys
import json
import time
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
BASE_DIR = Path(r"C:\backup\projects\edutech")
BACKUP_DIR = BASE_DIR / "backups"
RETENTION_DAYS = 30

def bootstrap_django():
    """Bootstrap Django to use its ORM and configuration."""
    sys.path.insert(0, str(BASE_DIR))
    sys.path.insert(0, str(BASE_DIR / 'apps'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    import django
    django.setup()
    from django.conf import settings
    return settings

def extract_tenant_schema():
    """Extract tenant and domain information into a JSON manifest."""
    from django.apps import apps
    from django.conf import settings
    
    TenantModel = apps.get_model(settings.TENANT_MODEL)
    DomainModel = apps.get_model(settings.TENANT_DOMAIN_MODEL)
    
    tenants_data = []
    for tenant in TenantModel.objects.all():
        domains = [d.domain for d in DomainModel.objects.filter(tenant=tenant)]
        tenants_data.append({
            'schema_name': tenant.schema_name,
            'name': getattr(tenant, 'name', tenant.schema_name),
            'domains': domains
        })
        
    return tenants_data

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

def run_pg_dump(db_config, timestamp):
    """Execute pg_dump with gzip compression."""
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Files
    schema_file = BACKUP_DIR / f"tenants_manifest_{timestamp}.json"
    
    # Dump Schema JSON
    try:
        tenant_data = extract_tenant_schema()
        with open(schema_file, 'w') as f:
            json.dump(tenant_data, f, indent=4)
        logger.info(f"Tenant manifest saved to {schema_file}")
    except Exception as e:
        logger.error(f"Failed to extract tenant schema: {e}")
    
    # Run pg_dump (Custom format -Fc is naturally compressed and better for pg_restore)
    # Using PGPASSWORD environment variable for authentication
    dump_file = BACKUP_DIR / f"db_backup_{timestamp}.dump"
    
    env = os.environ.copy()
    env['PGPASSWORD'] = db_config['password']
    
    pg_dump_cmd = [
        "pg_dump",
        "-h", db_config['host'],
        "-p", db_config['port'],
        "-U", db_config['user'],
        "-Fc", # Custom format
        "-f", str(dump_file),
        db_config['name']
    ]
    
    logger.info("Starting pg_dump...")
    try:
        subprocess.run(pg_dump_cmd, env=env, check=True, capture_output=True)
        logger.info(f"Database successfully dumped to {dump_file}")
    except subprocess.CalledProcessError as e:
        logger.error(f"pg_dump failed: {e.stderr.decode()}")
        sys.exit(1)
        
    return dump_file

def upload_to_s3(file_path):
    """Optional S3 upload."""
    try:
        import boto3
    except ImportError:
        logger.warning("boto3 not installed. Skipping S3 upload.")
        return
        
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    if not bucket_name:
        logger.warning("AWS_STORAGE_BUCKET_NAME not set. Skipping S3 upload.")
        return
        
    s3 = boto3.client('s3')
    object_name = f"database_backups/{file_path.name}"
    
    logger.info(f"Uploading {file_path.name} to S3 bucket {bucket_name}...")
    try:
        s3.upload_file(str(file_path), bucket_name, object_name)
        logger.info("S3 upload successful.")
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")

def cleanup_old_backups():
    """Delete backups older than RETENTION_DAYS."""
    now = time.time()
    cutoff = now - (RETENTION_DAYS * 86400)
    
    if not BACKUP_DIR.exists():
        return
        
    for f in BACKUP_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            logger.info(f"Deleting old backup: {f.name}")
            f.unlink()

def main():
    logger.info("Starting backup process...")
    settings = bootstrap_django()
    db_config = get_db_config(settings)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    dump_file = run_pg_dump(db_config, timestamp)
    
    # Validate
    if dump_file.exists() and dump_file.stat().st_size > 1000:
        logger.info(f"Backup validation passed. Size: {dump_file.stat().st_size / (1024*1024):.2f} MB")
        upload_to_s3(dump_file)
        cleanup_old_backups()
        logger.info("Backup process completed successfully.")
    else:
        logger.error("Backup validation failed! File is too small or missing.")
        sys.exit(1)

if __name__ == "__main__":
    main()
