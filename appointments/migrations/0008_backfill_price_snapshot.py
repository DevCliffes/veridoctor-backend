from django.db import migrations


def backfill_price_snapshot(apps, schema_editor):
    ProviderAppointment = apps.get_model("appointments", "ProviderAppointment")
    appointments = ProviderAppointment.objects.filter(
        service__isnull=False, price_at_booking__isnull=True
    ).select_related("service")
    updated = []
    for appt in appointments:
        appt.price_at_booking = appt.service.price
        appt.currency_at_booking = appt.service.currency
        updated.append(appt)
    ProviderAppointment.objects.bulk_update(
        updated, ["price_at_booking", "currency_at_booking"], batch_size=500
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0007_add_price_snapshot_fields"),
    ]

    operations = [
        migrations.RunPython(backfill_price_snapshot, noop_reverse),
    ]
