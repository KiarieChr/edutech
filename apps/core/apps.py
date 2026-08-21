from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        import core.audit_signals  # noqa: F401 — register signal handlers
