from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        # Index rename skipped - production index name differs from what makemigrations expected.
        # Applied as no-op to keep migration history consistent.
    ]
