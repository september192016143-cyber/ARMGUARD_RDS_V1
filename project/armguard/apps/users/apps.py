from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'armguard.apps.users'

    def ready(self):
        """Connect the group→UserProfile sync signal once all models are loaded."""
        from django.contrib.auth import get_user_model
        from django.db.models.signals import m2m_changed
        from armguard.apps.users.models import on_user_groups_changed

        User = get_user_model()
        m2m_changed.connect(on_user_groups_changed, sender=User.groups.through)
