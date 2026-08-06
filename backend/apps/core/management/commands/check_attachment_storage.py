from django.core.management.base import BaseCommand, CommandError

from apps.core.storage_readiness import check_attachment_storage_writable


class Command(BaseCommand):
    help = (
        "Verifies ATTACHMENTS_LOCAL_ROOT exists and is writable by the current "
        "process, creating the root itself (not any other path) if it doesn't "
        "exist yet. Exits non-zero on failure. Intended for use at container "
        "startup, before the real process (gunicorn/celery) starts — see "
        "backend/entrypoint.sh."
    )

    def handle(self, *args, **options):
        result = check_attachment_storage_writable()
        if not result.ok:
            raise CommandError(f"Attachment storage is not usable: {result.detail}")
        self.stdout.write(self.style.SUCCESS("Attachment storage is writable."))
