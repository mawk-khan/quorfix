from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizations"

    def ready(self):
        # Registers OrganizationAwareSessionAuthenticationScheme with
        # drf-spectacular (see apps/organizations/schema.py) — the module
        # must be imported somewhere before schema generation runs, and an
        # AppConfig.ready() hook is the standard place to guarantee that.
        from apps.organizations import schema  # noqa: F401
