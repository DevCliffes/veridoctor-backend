from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0007_authcode"),
    ]

    operations = [
        # These fields already exist in production via hand-written ALTER TABLE.
        # This migration is intentionally empty — apply with --fake only.
    ]
