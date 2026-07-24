from django.db import migrations


def backfill_schedule_locations(apps, schema_editor):
    """
    Existing ProviderSchedule rows predate the `location` FK and were
    created back when a provider only ever had one facility. For any
    physical/both block still missing a location, attach it to that
    provider's primary location (falling back to the oldest location if
    for some reason none is flagged primary). Virtual blocks are left
    alone -- location-less is correct for them, not a gap to fill.

    A block is silently left with location=None if the provider somehow
    has zero locations at all (shouldn't happen for anyone who's gotten
    through onboarding, but this must not crash the migration for an
    edge-case/test account).
    """
    ProviderSchedule = apps.get_model("provider", "ProviderSchedule")
    ProviderLocation = apps.get_model("provider", "ProviderLocation")

    schedules = ProviderSchedule.objects.filter(
        location__isnull=True,
        location_type__in=["physical", "both"],
    ).select_related("provider")

    # Cache one lookup per provider rather than requerying per schedule --
    # a provider can have many schedule blocks.
    primary_location_cache = {}

    for schedule in schedules:
        provider_id = schedule.provider_id
        if provider_id not in primary_location_cache:
            location = (
                ProviderLocation.objects.filter(provider_id=provider_id, is_primary=True).first()
                or ProviderLocation.objects.filter(provider_id=provider_id).order_by("created_at").first()
            )
            primary_location_cache[provider_id] = location

        location = primary_location_cache[provider_id]
        if location is not None:
            schedule.location = location
            schedule.save(update_fields=["location"])


def noop_reverse(apps, schema_editor):
    # Deliberately a no-op. Reversing this would mean stripping location
    # off every schedule this backfill touched, which isn't safely
    # reconstructible (we'd be guessing which ones were auto-filled vs.
    # deliberately set afterward by the provider) and isn't something
    # you'd ever actually want mid-rollback anyway -- the field itself
    # unmigrating is handled by 0016, not this one.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0016_add_location_to_providerschedule"),
    ]

    operations = [
        migrations.RunPython(backfill_schedule_locations, noop_reverse),
    ]
