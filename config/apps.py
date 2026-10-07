from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class EidrenAdminConfig(AdminConfig):
    default_site = "config.admin.EidrenAdminSite"


class PlatformConfig(AppConfig):
    name = "config"
    verbose_name = "Platform"
