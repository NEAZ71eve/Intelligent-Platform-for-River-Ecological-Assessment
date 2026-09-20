from django.apps import AppConfig


class LLMConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'llm'
    verbose_name = 'AI 解读网关'

    def ready(self):
        from . import signals  # noqa: F401
