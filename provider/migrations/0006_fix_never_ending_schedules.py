from django.db import migrations


def fix_never_ending_schedules(apps, schema_editor):
    ProviderSchedule = apps.get_model("provider", "ProviderSchedule")
    ProviderSchedule.objects.filter(
        recurrence__in=["daily", "weekly", "weekdays", "custom"],
        recurrence_end_type__in=[None, "never", ""],
    ).update(end_date="2099-12-31")


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0005_sync_provider_models"),
    ]

    operations = [
        migrations.RunPython(fix_never_ending_schedules, migrations.RunPython.noop),
    ]
