from django.apps import AppConfig


class AssetsConfig(AppConfig):
    name = 'assets'
    verbose_name = '私有文件'

    def ready(self):
        from . import signals  # noqa: F401

