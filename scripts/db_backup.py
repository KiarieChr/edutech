#!/usr/bin/env python
import os
import sys
import json
import time
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "backups"
RETENTION_DAYS = 30

def bootstrap_django():
    """Bootstrap Django to use its ORM and configuration."""
    sys.path.insert(0, str(BASE_DIR))
    sys.path.insert(0, str(BASE_DIR / 'apps'))
    
    # Priority to production settings unless explicitly overridden
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

    # Load .env file into environment if present
    env_file = BASE_DIR / '.env'
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        except Exception as e:
            logger.warning(f"Failed to read .env file: {e}")

    # Polyfills for compatibility
    try:
        import django.utils.encoding
        if not hasattr(django.utils.encoding, 'python_2_unicode_compatible'):
            django.utils.encoding.python_2_unicode_compatible = lambda x: x
        if not hasattr(django.utils.encoding, 'smart_text'):
            django.utils.encoding.smart_text = getattr(django.utils.encoding, 'smart_str', lambda x: str(x))
        if not hasattr(django.utils.encoding, 'force_text'):
            django.utils.encoding.force_text = getattr(django.utils.encoding, 'force_str', lambda x: str(x))
        
        import django.utils.translation
        if not hasattr(django.utils.translation, 'ugettext_lazy'):
            django.utils.translation.ugettext_lazy = getattr(django.utils.translation, 'gettext_lazy', lambda x: x)
        if not hasattr(django.utils.translation, 'ugettext'):
            django.utils.translation.ugettext = getattr(django.utils.translation, 'gettext', lambda x: x)
        if not hasattr(django.utils.translation, 'ungettext_lazy'):
            django.utils.translation.ungettext_lazy = getattr(django.utils.translation, 'ngettext_lazy', lambda x, y, z: x)
        
        import django.urls
        try:
            import django.conf.urls
            if not hasattr(django.conf.urls, 'url'):
                django.conf.urls.url = getattr(django.urls, 're_path', None)
        except ImportError:
            import types
            urls_mod = types.ModuleType('django.conf.urls')
            urls_mod.url = getattr(django.urls, 're_path', None)
            urls_mod.include = getattr(django.urls, 'include', None)
            sys.modules['django.conf.urls'] = urls_mod
    except ImportError:
        pass

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
        'host': db.get('HOST') or 'localhost',
        'port': str(db.get('PORT') or '5432'),
        'user': db.get('USER') or 'postgres',
        'password': db.get('PASSWORD') or '',
        'name': db.get('NAME') or 'edutechdb'
    }

def get_pg_bin(binary_name):
    """Get the full path to a postgres binary on Windows, or just the name on Linux."""
    import shutil
    if os.name == 'nt':
        if shutil.which(binary_name):
            return binary_name
        for version in ["17", "16", "15", "14", "13", "12"]:
            path = Path(f"C:\\Program Files\\PostgreSQL\\{version}\\bin\\{binary_name}.exe")
            if path.exists():
                return str(path)
    return binary_name

def run_pg_dump(db_config, timestamp):
    """Execute pg_dump."""
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Files
    schema_file = BACKUP_DIR / f"tenants_manifest_{timestamp}.json"
    
    # Dump Schema JSON
    try:
        tenant_data = extract_tenant_schema()
        with open(schema_file, 'w', encoding='utf-8') as f:
            json.dump(tenant_data, f, indent=4)
        logger.info(f"Tenant manifest saved to {schema_file}")
    except Exception as e:
        logger.warning(f"Could not extract tenant schema manifest: {e}")
    
    # Run pg_dump (Plain SQL format is portable across Postgres versions)
    dump_file = BACKUP_DIR / f"db_backup_{timestamp}.sql"
    
    env = os.environ.copy()
    if db_config.get('password'):
        env['PGPASSWORD'] = str(db_config['password'])
    
    pg_dump_bin = get_pg_bin("pg_dump")
    
    pg_dump_cmd = [
        pg_dump_bin,
        "-h", db_config['host'],
        "-p", db_config['port'],
        "-U", db_config['user'],
        "-F", "p",
        "-f", str(dump_file),
        db_config['name']
    ]
    
    logger.info(f"Starting pg_dump for database '{db_config['name']}' at {db_config['host']}:{db_config['port']}...")
    try:
        subprocess.run(pg_dump_cmd, env=env, check=True, capture_output=True)
        logger.info(f"Database successfully dumped to {dump_file}")
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        logger.error(f"pg_dump failed: {err_msg}")
        raise
        
    return dump_file

def upload_to_s3(file_path):
    """Optional S3 upload."""
    try:
        import boto3
    except ImportError:
        return
        
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    if not bucket_name:
        return
        
    try:
        s3 = boto3.client('s3')
        object_name = f"database_backups/{file_path.name}"
        logger.info(f"Uploading {file_path.name} to S3 bucket {bucket_name}...")
        s3.upload_file(str(file_path), bucket_name, object_name)
        logger.info("S3 upload successful.")
    except Exception as e:
        logger.warning(f"S3 upload failed: {e}")

def cleanup_old_backups():
    """Delete backups older than RETENTION_DAYS."""
    now = time.time()
    cutoff = now - (RETENTION_DAYS * 86400)
    
    if not BACKUP_DIR.exists():
        return
        
    for f in BACKUP_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            logger.info(f"Deleting old backup: {f.name}")
            try:
                f.unlink()
            except Exception:
                pass

def main():
    logger.info("Starting backup process...")
    settings = bootstrap_django()
    db_config = get_db_config(settings)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        dump_file = run_pg_dump(db_config, timestamp)
        if dump_file.exists() and dump_file.stat().st_size > 100:
            logger.info(f"Backup validation passed. Size: {dump_file.stat().st_size / (1024*1024):.2f} MB")
            upload_to_s3(dump_file)
            cleanup_old_backups()
            logger.info("Backup process completed successfully.")
        else:
            logger.warning("Backup file is empty or missing.")
    except Exception as e:
        logger.error(f"Database backup encountered an error: {e}")
        # Exit with error code so caller knows, but script can handle with warning
        sys.exit(1)

if __name__ == "__main__":
    main()

