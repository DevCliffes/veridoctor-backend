from django.db import migrations

# The five facility-document field names that used to live on
# HealthcareProvider/ProviderDocumentReview and now belong on
# ProviderLocation/ProviderLocationDocumentReview.
FACILITY_FIELD_NAMES = [
    "clinic_logo_url",
    "business_reg_image",
    "operating_licence_image",
    "kra_pin_image",
    "cr12_image",
]

# Plain (non-document) facility fields copied straight across from
# HealthcareProvider onto the new ProviderLocation row.
FACILITY_TEXT_FIELD_MAP = {
    "name": "clinic_name",
    "address": "address",
    "county": "county",
    "country": "country",
    "clinic_logo_url": "clinic_logo_url",
    "business_reg_number": "business_reg_number",
    "business_reg_image": "business_reg_image",
    "operating_licence": "operating_licence",
    "operating_licence_image": "operating_licence_image",
    "kra_pin": "kra_pin",
    "kra_pin_image": "kra_pin_image",
    "cr12_image": "cr12_image",
}


def backfill_locations(apps, schema_editor):
    HealthcareProvider = apps.get_model("provider", "HealthcareProvider")
    ProviderLocation = apps.get_model("provider", "ProviderLocation")
    ProviderDocumentReview = apps.get_model("provider", "ProviderDocumentReview")
    ProviderLocationDocumentReview = apps.get_model("provider", "ProviderLocationDocumentReview")

    for provider in HealthcareProvider.objects.all():
        location = ProviderLocation.objects.create(
            provider=provider,
            is_primary=True,
            **{
                new_field: (getattr(provider, old_field, "") or "")
                for new_field, old_field in FACILITY_TEXT_FIELD_MAP.items()
            },
        )

        # data_complete / is_fully_approved_cache are computed in
        # ProviderLocation.save() in real code, but historical models in
        # a data migration don't run that custom save() logic -- so
        # compute the initial values here explicitly instead.
        required_text = ["name", "address", "county", "business_reg_number", "operating_licence", "kra_pin"]
        required_images = FACILITY_FIELD_NAMES
        missing = [
            f for f in required_text + required_images
            if not str(getattr(location, f, "") or "").strip()
        ]
        location.data_complete = len(missing) == 0

        # Move any existing facility-document reviews for this provider
        # over to the new location, preserving status/rejection detail.
        old_reviews = ProviderDocumentReview.objects.filter(
            provider=provider, field_name__in=FACILITY_FIELD_NAMES
        )
        approved_fields = set()
        for old_review in old_reviews:
            ProviderLocationDocumentReview.objects.create(
                location=location,
                field_name=old_review.field_name,
                document_url=old_review.document_url,
                status=old_review.status,
                rejection_category=old_review.rejection_category,
                rejection_reason=old_review.rejection_reason,
                reviewed_at=old_review.reviewed_at,
                reviewed_by=old_review.reviewed_by,
            )
            if old_review.status == "approved":
                approved_fields.add(old_review.field_name)

        location.is_fully_approved_cache = set(FACILITY_FIELD_NAMES).issubset(approved_fields)
        location.save()

    # Clean up: the old facility rows on ProviderDocumentReview have now
    # been copied to ProviderLocationDocumentReview above. Delete the
    # originals so they don't linger under a field_name choice that
    # migration 0014 is about to remove from ProviderDocumentReview.
    ProviderDocumentReview.objects.filter(field_name__in=FACILITY_FIELD_NAMES).delete()


def reverse_backfill(apps, schema_editor):
    # Best-effort reverse: copy each provider's primary location's data
    # back onto HealthcareProvider's (still-present, at this point in
    # the reverse sequence) facility fields, then drop the locations.
    # ProviderDocumentReview rows deleted by the forward migration are
    # NOT recreated -- if you need to reverse past this point, restore
    # from a DB backup taken before running 0013 instead.
    HealthcareProvider = apps.get_model("provider", "HealthcareProvider")
    ProviderLocation = apps.get_model("provider", "ProviderLocation")

    for provider in HealthcareProvider.objects.all():
        location = ProviderLocation.objects.filter(provider=provider, is_primary=True).first()
        if not location:
            continue
        for new_field, old_field in FACILITY_TEXT_FIELD_MAP.items():
            setattr(provider, old_field, getattr(location, new_field, ""))
        provider.save()

    ProviderLocation.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0012_add_providerlocation"),
    ]

    operations = [
        migrations.RunPython(backfill_locations, reverse_backfill),
    ]
