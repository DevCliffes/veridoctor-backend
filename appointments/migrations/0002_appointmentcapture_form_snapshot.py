from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="appointmentcapture",
                    name="form_snapshot",
                    field=models.JSONField(blank=True, default=list),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
ALTER TABLE appointments_appointmentcapture
    ADD COLUMN IF NOT EXISTS form_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
