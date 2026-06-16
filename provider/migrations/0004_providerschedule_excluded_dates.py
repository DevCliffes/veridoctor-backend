from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('provider', '0003_providerschedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='providerschedule',
            name='excluded_dates',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='ISO date strings (YYYY-MM-DD) to skip for recurring schedules — used when deleting/editing a single occurrence instead of the whole series.'
            ),
        ),
    ]
