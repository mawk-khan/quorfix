import tarfile

from django.core.management.base import BaseCommand, CommandError

from apps.core.tar_safety import UnsafeTarMemberError, safe_extract_all


class Command(BaseCommand):
    help = (
        "Validates and extracts a local-attachments backup archive (see "
        "scripts/backup_attachments.sh) into a destination directory, refusing to extract "
        "anything if any archive member is unsafe (an absolute path, a '..' traversal, a "
        "symlink, or a special/device file). Invoked by scripts/restore_attachments.sh "
        "after that script's own confirmation and checksum checks — not a substitute for "
        "them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--archive", required=True, help="Path to the attachments.tar.gz archive"
        )
        parser.add_argument("--destination", required=True, help="Directory to extract into")

    def handle(self, *args, **options):
        archive = options["archive"]
        destination = options["destination"]
        try:
            count = safe_extract_all(archive, destination)
        except UnsafeTarMemberError as exc:
            raise CommandError(f"Refusing to extract archive: {exc}") from None
        except tarfile.TarError as exc:
            raise CommandError(f"Archive is not a valid tar file: {exc}") from None
        except OSError as exc:
            raise CommandError(f"Could not extract archive: {exc.strerror or exc}") from None
        self.stdout.write(
            self.style.SUCCESS(f"Extracted {count} archive member(s) to {destination}")
        )
