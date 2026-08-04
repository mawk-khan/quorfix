from django.db import migrations


def seed_setup_lock(apps, schema_editor):
    SetupLock = apps.get_model("organizations", "SetupLock")
    SetupLock.objects.get_or_create(id=1)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_setup_lock, noop_reverse),
    ]
