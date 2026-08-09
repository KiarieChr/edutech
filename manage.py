#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# --- Polyfills for older packages like django-jet ---
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
    
    import sys
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
# ----------------------------------------------------

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
