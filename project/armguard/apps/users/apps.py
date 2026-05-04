import logging
from django.apps import AppConfig

_startup_logger = logging.getLogger('armguard.system')
_startup_logged = False


def _log_startup_once(sender, **kwargs):
    """Write a STARTUP SystemLog entry on the first HTTP request of each worker.

    Deferred from AppConfig.ready() to avoid the Django RuntimeWarning about
    DB access during app initialization (which fires on every Gunicorn worker
    spawn and pollutes gunicorn.log).
    """
    global _startup_logged
    if _startup_logged:
        return
    _startup_logged = True
    # Disconnect immediately so this never runs again in this worker process.
    from django.core.signals import request_started
    request_started.disconnect(_log_startup_once)
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



class UsersConfig(AppConfig):
    name = 'armguard.apps.users'

    def ready(self):
        """Connect signals and schedule a deferred startup SystemLog entry."""
        from django.contrib.auth import get_user_model
        from django.db.models.signals import m2m_changed
        from armguard.apps.users.models import on_user_groups_changed

        User = get_user_model()
        m2m_changed.connect(on_user_groups_changed, sender=User.groups.through)

        # Record application startup in SystemLog on the first request rather
        # than in ready(), which would trigger Django's "DB access during app
        # initialization" RuntimeWarning on every Gunicorn worker spawn.
        from django.core.signals import request_started
        request_started.connect(_log_startup_once)
