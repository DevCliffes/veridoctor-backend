from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    HealthcareProvider,
    ProviderDocumentReview,
    ProviderLocation,
    ProviderLocationDocumentReview,
)


# ── Personal/professional documents (live on HealthcareProvider) ───────────
# Maps each personal document image field to the corresponding "number"
# field on HealthcareProvider, so the admin can show the submitted
# document image and the number the provider typed in side by side.
FIELD_TO_NUMBER_FIELD = {
    "national_id_image": ("national_id_number", "National ID / Passport number"),
    "valid_licence_image": ("valid_licence_number", "Valid operating licence number"),
}

# ── Facility documents (now live on ProviderLocation) ──────────────────────
# Same idea as FIELD_TO_NUMBER_FIELD above, but the "number" field being
# compared against lives on the ProviderLocation, not the provider itself,
# since a provider can have several locations each with their own numbers.
LOCATION_FIELD_TO_NUMBER_FIELD = {
    "business_reg_image": ("business_reg_number", "Business registration number"),
    "operating_licence_image": ("operating_licence", "Operating licence number"),
    "kra_pin_image": ("kra_pin", "KRA PIN"),
    "clinic_logo_url": (None, None),
    "cr12_image": (None, None),
}


def _number_value_for(review):
    """Returns the typed value the provider entered for the number field
    that corresponds to this personal document, or "" if this document
    type has no matching number field."""
    number_field, _ = FIELD_TO_NUMBER_FIELD.get(review.field_name, (None, None))
    if not number_field:
        return ""
    return getattr(review.provider, number_field, "") or ""


def _location_number_value_for(review):
    """Same as _number_value_for, but for a ProviderLocationDocumentReview
    -- reads the number field off review.location instead of a provider."""
    number_field, _ = LOCATION_FIELD_TO_NUMBER_FIELD.get(review.field_name, (None, None))
    if not number_field:
        return ""
    return getattr(review.location, number_field, "") or ""


def _refresh_location_approval_cache(location):
    """Recomputes and saves ProviderLocation.is_fully_approved_cache after
    a document review changes. Safe to call after any approve/reject --
    is_fully_approved_cache is not one of the tracked fields that trigger
    ProviderLocation.save()'s "reset all reviews to pending" behaviour,
    so this can't accidentally undo the very approval we just recorded."""
    location.is_fully_approved_cache = location.recompute_is_fully_approved()
    location.save(update_fields=["is_fully_approved_cache", "data_complete", "updated_at"])


def _notify_provider_of_review(review):
    """
    Notifies the provider in-app when one of their personal documents is
    approved or rejected, so they don't have to keep checking back
    manually. Wrapped in try/except to match the existing _notify()
    pattern in appointments/views.py -- a notification failure should
    never block the actual approve/reject action from saving.

    `link` points at /profile#<field_name> -- the field_name matches the
    `id` attribute on that document's upload control in the profile page,
    so clicking the notification scrolls the doctor straight to the
    flagged document instead of dropping them at the top of a long form
    to hunt for it themselves.
    """
    try:
        from notifications.models import Notification

        identity = review.provider.identity
        field_label = review.get_field_name_display()

        if review.status == ProviderDocumentReview.STATUS_APPROVED:
            title = "Document approved"
            message = f"Your {field_label} has been approved."
        elif review.status == ProviderDocumentReview.STATUS_REJECTED:
            category_label = review.get_rejection_category_display() or "an issue"
            detail = f" {review.rejection_reason}" if review.rejection_reason else ""
            title = "Document needs re-upload"
            message = f"Your {field_label} was rejected ({category_label}).{detail}".strip()
        else:
            return

        Notification.objects.create(
            recipient_identity=identity,
            notification_type="document_reviewed",
            title=title,
            message=message,
            link=f"/profile#{review.field_name}",
        )
    except Exception:
        pass


def _notify_provider_of_location_review(review):
    """
    Same as _notify_provider_of_review, but for a facility document tied
    to a specific ProviderLocation. The notification link includes the
    location id (`/profile#location-<id>-<field_name>`) so the frontend
    can scroll to the right location card once a provider has more than
    one -- exact anchor format to be finalized alongside the frontend
    "My Locations" UI.
    """
    try:
        from notifications.models import Notification

        location = review.location
        identity = location.provider.identity
        field_label = review.get_field_name_display()
        location_label = location.name or "your location"

        if review.status == ProviderLocationDocumentReview.STATUS_APPROVED:
            title = "Document approved"
            message = f"The {field_label} for {location_label} has been approved."
        elif review.status == ProviderLocationDocumentReview.STATUS_REJECTED:
            category_label = review.get_rejection_category_display() or "an issue"
            detail = f" {review.rejection_reason}" if review.rejection_reason else ""
            title = "Document needs re-upload"
            message = (
                f"The {field_label} for {location_label} was rejected "
                f"({category_label}).{detail}"
            ).strip()
        else:
            return

        Notification.objects.create(
            recipient_identity=identity,
            notification_type="document_reviewed",
            title=title,
            message=message,
            link=f"/profile#location-{location.id}-{review.field_name}",
        )
    except Exception:
        pass


class ProviderDocumentReviewInline(admin.TabularInline):
    """
    Read-only glance at a provider's personal document statuses from
    within the HealthcareProvider admin page. Actual approve/reject with
    a reason happens on the ProviderDocumentReview list page below.
    """
    model = ProviderDocumentReview
    extra = 0
    fields = ("field_name", "status", "thumbnail", "number_value", "rejection_category", "rejection_reason", "updated_at")
    readonly_fields = ("field_name", "thumbnail", "number_value", "updated_at")
    can_delete = False
    ordering = ("-updated_at",)

    def thumbnail(self, obj):
        if obj.document_url:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:80px;border-radius:4px;"/></a>',
                obj.document_url,
            )
        return "—"
    thumbnail.short_description = "Preview"

    def number_value(self, obj):
        value = _number_value_for(obj)
        _, label = FIELD_TO_NUMBER_FIELD.get(obj.field_name, (None, None))
        if not label:
            return "—"
        return value or "— not provided —"
    number_value.short_description = "Submitted number"

    def has_add_permission(self, request, obj=None):
        return False


class ProviderLocationInline(admin.TabularInline):
    """
    Read-only glance at a provider's locations from within the
    HealthcareProvider admin page. Click through to the ProviderLocation
    admin page below to actually review its documents.
    """
    model = ProviderLocation
    extra = 0
    fields = ("name", "county", "is_primary", "data_complete", "is_fully_approved_cache", "created_at")
    readonly_fields = ("name", "county", "is_primary", "data_complete", "is_fully_approved_cache", "created_at")
    can_delete = False
    ordering = ("-is_primary", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HealthcareProvider)
class HealthcareProviderAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "speciality", "profile_complete", "is_bookable",
        "locations_count", "pending_documents_count", "rejected_documents_count",
    )
    list_filter = ("profile_complete", "speciality")
    search_fields = (
        "identity__first_name", "identity__last_name", "identity__email",
    )
    inlines = [ProviderDocumentReviewInline, ProviderLocationInline]

    def locations_count(self, obj):
        return obj.locations.count()
    locations_count.short_description = "Locations"

    def pending_documents_count(self, obj):
        return obj.document_reviews.filter(status=ProviderDocumentReview.STATUS_PENDING).count()
    pending_documents_count.short_description = "Pending docs (personal)"

    def rejected_documents_count(self, obj):
        return obj.document_reviews.filter(status=ProviderDocumentReview.STATUS_REJECTED).count()
    rejected_documents_count.short_description = "Rejected docs (personal)"


@admin.register(ProviderDocumentReview)
class ProviderDocumentReviewAdmin(admin.ModelAdmin):
    """
    Review queue for personal/professional documents (National ID, valid
    operating licence). Facility documents now have their own queue --
    see ProviderLocationDocumentReviewAdmin below.

    Ordered by -updated_at (rather than provider/field_name) so that a
    document a provider just re-uploaded after a rejection naturally
    floats to the top of the "Pending review" filter -- no separate
    "resubmitted" status is needed to surface it; recency does that job
    on its own.
    """
    list_display = (
        "provider_name", "field_name", "status", "thumbnail", "number_value_column",
        "rejection_category", "rejection_reason", "updated_at",
    )
    list_filter = ("status", "field_name", "rejection_category")
    search_fields = (
        "provider__identity__first_name",
        "provider__identity__last_name",
        "provider__identity__email",
    )
    ordering = ("-updated_at",)
    readonly_fields = (
        "provider", "field_name", "document_url", "large_preview",
        "created_at", "updated_at", "reviewed_at", "reviewed_by",
    )
    fields = (
        "provider", "field_name", "large_preview", "document_url",
        "status", "rejection_category", "rejection_reason",
        "reviewed_at", "reviewed_by", "created_at", "updated_at",
    )
    actions = ["approve_selected", "reject_selected"]

    def provider_name(self, obj):
        identity = obj.provider.identity
        return f"{identity.first_name} {identity.last_name}"
    provider_name.short_description = "Provider"

    def thumbnail(self, obj):
        if obj.document_url:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:60px;border-radius:4px;"/></a>',
                obj.document_url,
            )
        return "—"
    thumbnail.short_description = "Preview"

    def number_value_column(self, obj):
        value = _number_value_for(obj)
        _, label = FIELD_TO_NUMBER_FIELD.get(obj.field_name, (None, None))
        if not label:
            return "—"
        return value or "— not provided —"
    number_value_column.short_description = "Submitted number"

    def large_preview(self, obj):
        """
        Side-by-side comparison view shown on the document's detail page:
        the submitted document image, the number the provider typed for
        it (so a mismatch jumps out immediately), and -- for the National
        ID / Passport specifically -- the provider's submitted profile
        photo right alongside it, so the reviewer can visually confirm the
        ID belongs to the same person as the profile.
        """
        if not obj.document_url:
            return "No document uploaded"

        number_field, number_label = FIELD_TO_NUMBER_FIELD.get(obj.field_name, (None, None))
        number_value = getattr(obj.provider, number_field, "") if number_field else ""

        fragments = [
            '<div style="display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap;">'
        ]

        fragments.append(format_html(
            '<div><p style="margin:0 0 6px; font-weight:600; color:#374151;">Submitted document</p>'
            '<a href="{0}" target="_blank">'
            '<img src="{0}" style="max-height:420px; max-width:420px; border-radius:6px; '
            'border:1px solid #e5e7eb;"/></a></div>',
            obj.document_url,
        ))

        if number_field:
            fragments.append(format_html(
                '<div style="min-width:220px;"><p style="margin:0 0 6px; font-weight:600; '
                'color:#374151;">{0}</p>'
                '<p style="font-size:18px; font-family:monospace; background:#f3f4f6; '
                'padding:8px 12px; border-radius:6px; display:inline-block;">{1}</p></div>',
                number_label,
                number_value or "— not provided —",
            ))

        if obj.field_name == "national_id_image":
            profile_photo = obj.provider.profile_picture_url or ""
            if profile_photo:
                photo_html = format_html(
                    '<img src="{0}" style="max-height:420px; max-width:320px; border-radius:6px; '
                    'border:1px solid #e5e7eb;"/>',
                    profile_photo,
                )
            else:
                photo_html = format_html('<p style="color:#9ca3af;">No profile photo submitted</p>')
            fragments.append(format_html(
                '<div><p style="margin:0 0 6px; font-weight:600; color:#374151;">'
                'Submitted profile photo (check this matches the ID)</p>{0}</div>',
                photo_html,
            ))

        fragments.append('</div>')
        return mark_safe("".join(str(f) for f in fragments))
    large_preview.short_description = "Document"

    def save_model(self, request, obj, form, change):
        # Whenever status changes via the detail page (this is also where
        # a reviewer sets rejection_category + rejection_reason before
        # saving a rejection), stamp who reviewed it, when, and notify
        # the provider.
        status_changed = change and "status" in form.changed_data
        if status_changed:
            obj.reviewed_at = timezone.now()
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)
        if status_changed:
            _notify_provider_of_review(obj)

    def approve_selected(self, request, queryset):
        count = 0
        for review in queryset:
            review.status = ProviderDocumentReview.STATUS_APPROVED
            review.rejection_category = ""
            review.rejection_reason = ""
            review.reviewed_at = timezone.now()
            review.reviewed_by = request.user
            review.save()
            _notify_provider_of_review(review)
            count += 1
        self.message_user(request, f"{count} document(s) approved.")
    approve_selected.short_description = "Approve selected documents"

    def reject_selected(self, request, queryset):
        # Bulk reject applies a generic "other" category with no detail.
        # For a specific category + written reason, open the individual
        # record and set those fields there before saving.
        count = 0
        for review in queryset:
            review.status = ProviderDocumentReview.STATUS_REJECTED
            if not review.rejection_category:
                review.rejection_category = ProviderDocumentReview.REJECTION_OTHER
            review.reviewed_at = timezone.now()
            review.reviewed_by = request.user
            review.save()
            _notify_provider_of_review(review)
            count += 1
        self.message_user(
            request,
            f"{count} document(s) rejected. Edit each one individually to set a specific category/reason.",
        )
    reject_selected.short_description = "Reject selected documents (generic reason)"


class ProviderLocationDocumentReviewInline(admin.TabularInline):
    """
    Read-only glance at a location's document statuses from within the
    ProviderLocation admin page. Actual approve/reject with a reason
    happens on the ProviderLocationDocumentReview list page below.
    """
    model = ProviderLocationDocumentReview
    extra = 0
    fields = ("field_name", "status", "thumbnail", "number_value", "rejection_category", "rejection_reason", "updated_at")
    readonly_fields = ("field_name", "thumbnail", "number_value", "updated_at")
    can_delete = False
    ordering = ("-updated_at",)

    def thumbnail(self, obj):
        if obj.document_url:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:80px;border-radius:4px;"/></a>',
                obj.document_url,
            )
        return "—"
    thumbnail.short_description = "Preview"

    def number_value(self, obj):
        value = _location_number_value_for(obj)
        _, label = LOCATION_FIELD_TO_NUMBER_FIELD.get(obj.field_name, (None, None))
        if not label:
            return "—"
        return value or "— not provided —"
    number_value.short_description = "Submitted number"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProviderLocation)
class ProviderLocationAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "provider_name", "county", "is_primary",
        "data_complete", "is_fully_approved_cache",
        "pending_documents_count", "rejected_documents_count", "updated_at",
    )
    list_filter = ("is_primary", "data_complete", "is_fully_approved_cache", "county")
    search_fields = (
        "name",
        "provider__identity__first_name",
        "provider__identity__last_name",
        "provider__identity__email",
    )
    inlines = [ProviderLocationDocumentReviewInline]

    def provider_name(self, obj):
        identity = obj.provider.identity
        return f"{identity.first_name} {identity.last_name}"
    provider_name.short_description = "Provider"

    def pending_documents_count(self, obj):
        return obj.document_reviews.filter(status=ProviderLocationDocumentReview.STATUS_PENDING).count()
    pending_documents_count.short_description = "Pending docs"

    def rejected_documents_count(self, obj):
        return obj.document_reviews.filter(status=ProviderLocationDocumentReview.STATUS_REJECTED).count()
    rejected_documents_count.short_description = "Rejected docs"


@admin.register(ProviderLocationDocumentReview)
class ProviderLocationDocumentReviewAdmin(admin.ModelAdmin):
    """
    The facility-document review queue -- the location-scoped counterpart
    to ProviderDocumentReviewAdmin above. Filter by status/field, click
    into a row to approve or reject with a category + specific written
    reason, or select multiple rows and use the bulk actions for quick
    sweeps.

    Approving/rejecting here also refreshes the location's
    is_fully_approved_cache, which is what actually gates
    HealthcareProvider.is_bookable -- so a location only becomes
    (or stops being) bookable the moment its review queue changes here.
    """
    list_display = (
        "location_name", "provider_name", "field_name", "status", "thumbnail",
        "number_value_column", "rejection_category", "rejection_reason", "updated_at",
    )
    list_filter = ("status", "field_name", "rejection_category")
    search_fields = (
        "location__name",
        "location__provider__identity__first_name",
        "location__provider__identity__last_name",
        "location__provider__identity__email",
    )
    ordering = ("-updated_at",)
    readonly_fields = (
        "location", "field_name", "document_url", "large_preview",
        "created_at", "updated_at", "reviewed_at", "reviewed_by",
    )
    fields = (
        "location", "field_name", "large_preview", "document_url",
        "status", "rejection_category", "rejection_reason",
        "reviewed_at", "reviewed_by", "created_at", "updated_at",
    )
    actions = ["approve_selected", "reject_selected"]

    def location_name(self, obj):
        return obj.location.name or "(unnamed location)"
    location_name.short_description = "Location"

    def provider_name(self, obj):
        identity = obj.location.provider.identity
        return f"{identity.first_name} {identity.last_name}"
    provider_name.short_description = "Provider"

    def thumbnail(self, obj):
        if obj.document_url:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:60px;border-radius:4px;"/></a>',
                obj.document_url,
            )
        return "—"
    thumbnail.short_description = "Preview"

    def number_value_column(self, obj):
        value = _location_number_value_for(obj)
        _, label = LOCATION_FIELD_TO_NUMBER_FIELD.get(obj.field_name, (None, None))
        if not label:
            return "—"
        return value or "— not provided —"
    number_value_column.short_description = "Submitted number"

    def large_preview(self, obj):
        """
        Side-by-side comparison view: the submitted document image, and
        the number the provider typed for it on this location (so a
        mismatch jumps out immediately). Unlike the personal-documents
        queue, there's no profile-photo comparison here -- facility
        documents don't have an equivalent identity check.
        """
        if not obj.document_url:
            return "No document uploaded"

        number_field, number_label = LOCATION_FIELD_TO_NUMBER_FIELD.get(obj.field_name, (None, None))
        number_value = getattr(obj.location, number_field, "") if number_field else ""

        fragments = [
            '<div style="display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap;">'
        ]

        fragments.append(format_html(
            '<div><p style="margin:0 0 6px; font-weight:600; color:#374151;">Submitted document</p>'
            '<a href="{0}" target="_blank">'
            '<img src="{0}" style="max-height:420px; max-width:420px; border-radius:6px; '
            'border:1px solid #e5e7eb;"/></a></div>',
            obj.document_url,
        ))

        if number_field:
            fragments.append(format_html(
                '<div style="min-width:220px;"><p style="margin:0 0 6px; font-weight:600; '
                'color:#374151;">{0}</p>'
                '<p style="font-size:18px; font-family:monospace; background:#f3f4f6; '
                'padding:8px 12px; border-radius:6px; display:inline-block;">{1}</p></div>',
                number_label,
                number_value or "— not provided —",
            ))

        fragments.append('</div>')
        return mark_safe("".join(str(f) for f in fragments))
    large_preview.short_description = "Document"

    def save_model(self, request, obj, form, change):
        status_changed = change and "status" in form.changed_data
        if status_changed:
            obj.reviewed_at = timezone.now()
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)
        if status_changed:
            _notify_provider_of_location_review(obj)
        _refresh_location_approval_cache(obj.location)

    def approve_selected(self, request, queryset):
        count = 0
        touched_locations = set()
        for review in queryset:
            review.status = ProviderLocationDocumentReview.STATUS_APPROVED
            review.rejection_category = ""
            review.rejection_reason = ""
            review.reviewed_at = timezone.now()
            review.reviewed_by = request.user
            review.save()
            _notify_provider_of_location_review(review)
            touched_locations.add(review.location_id)
            count += 1
        for location in ProviderLocation.objects.filter(id__in=touched_locations):
            _refresh_location_approval_cache(location)
        self.message_user(request, f"{count} document(s) approved.")
    approve_selected.short_description = "Approve selected documents"

    def reject_selected(self, request, queryset):
        # Bulk reject applies a generic "other" category with no detail.
        # For a specific category + written reason, open the individual
        # record and set those fields there before saving.
        count = 0
        touched_locations = set()
        for review in queryset:
            review.status = ProviderLocationDocumentReview.STATUS_REJECTED
            if not review.rejection_category:
                review.rejection_category = ProviderLocationDocumentReview.REJECTION_OTHER
            review.reviewed_at = timezone.now()
            review.reviewed_by = request.user
            review.save()
            _notify_provider_of_location_review(review)
            touched_locations.add(review.location_id)
            count += 1
        for location in ProviderLocation.objects.filter(id__in=touched_locations):
            _refresh_location_approval_cache(location)
        self.message_user(
            request,
            f"{count} document(s) rejected. Edit each one individually to set a specific category/reason.",
        )
    reject_selected.short_description = "Reject selected documents (generic reason)"
