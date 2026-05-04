import logging
from django.apps import AppConfig

_startup_logger = logging.getLogger('armguard.system')


class UsersConfig(AppConfig):
    name = 'armguard.apps.users'

    def ready(self):
        """Connect signals and write a startup SystemLog entry."""
        from django.contrib.auth import get_user_model
        from django.db.models.signals import m2m_changed
        from armguard.apps.users.models import on_user_groups_changed

        User = get_user_model()
        m2m_changed.connect(on_user_groups_changed, sender=User.groups.through)

        # Record application startup in SystemLog. Wrapped in try/except so a
        # missing DB table (first migration) never prevents the server from starting.
        try:
            from armguard.apps.users.models import log_system_event
            import django
            log_system_event(
                'STARTUP', 'app_ready',
                message='ArmGuard RDS application started.',
                django_version=django.__version__,
            )
        except Exception as exc:
            _startup_logger.debug('Startup SystemLog skipped (DB not ready?): %s', exc)
