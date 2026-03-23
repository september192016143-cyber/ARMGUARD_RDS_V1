from django.apps import AppConfig


class ProfileConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'armguard.apps.profile'
    verbose_name = 'User Profile'
