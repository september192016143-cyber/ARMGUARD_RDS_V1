from django.apps import AppConfig


class TransactionsConfig(AppConfig):
    name = 'armguard.apps.transactions'

    def ready(self):
        import armguard.apps.transactions.signals  # noqa: F401  # N5: connect audit signals
