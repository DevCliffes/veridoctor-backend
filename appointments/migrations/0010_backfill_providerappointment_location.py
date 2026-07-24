from django.db import migrations


def backfill_appointment_locations(apps, schema_editor):
    """
    Mirrors the logic used in provider/migrations/0017 for
    ProviderSchedule: any existing *physical* appointment with no
    location gets the provider's primary (or oldest approved) location,
    where that's unambiguous. Virtual appointments are left untouched --
    they're location-less by design. Appointments for a provider with no
    approved locations at all (or where "primary" can't be determined)
    are left null; nothing here invents data that isn't there.
    """
    ProviderAppointment = apps.get_model("appointments", "ProviderAppointment")
    ProviderLocation = apps.get_model("provider", "ProviderLocation")

    providers_needing_backfill = (
        ProviderAppointment.objects.filter(
            appointment_type="physical", location__isnull=True
        )
        .values_list("provider_id", flat=True)
        .distinct()
    )

    for provider_id in providers_needing_backfill:
        locations_qs = ProviderLocation.objects.filter(
            provider_id=provider_id, approved=True
        ).order_by("created_at")

        location = (
            locations_qs.filter(is_primary=True).first()
            or locations_qs.first()
        )
        if location is None:
            continue

        ProviderAppointment.objects.filter(
            provider_id=provider_id,
            appointment_type="physical",
            location__isnull=True,
        ).update(location_id=location.id)


def noop_reverse(apps, schema_editor):
    # Intentionally irreversible in the sense of "undoing" the backfill --
    # we don't want to null out locations that may have since been relied
    # on elsewhere. Reversing this migration just leaves the data as-is.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0009_add_location_to_providerappointment"),
    ]

    operations = [
        migrations.RunPython(backfill_appointment_locations, noop_reverse),
    ]
