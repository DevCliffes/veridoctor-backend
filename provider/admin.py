from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import HealthcareProvider, ProviderDocumentReview


def _notify_provider_of_review(review):
    """
    Notifies the provider in-app when one of their documents is approved
    or rejected, so they don't have to keep checking back manually.
    Wrapped in try/except to match the existing _notify() pattern in
    appointments/views.py -- a notification failure should never block
    the actual approve/reject action from saving.
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
            notification_type="document_review",
            title=title,
            message=message,
            link="/provider/documents",
        )
    except Exception:
        pass


class ProviderDocumentReviewInline(admin.TabularInline):
    """
    Read-only glance at a provider's document statuses from within the
    HealthcareProvider admin page. Actual approve/reject with a reason
    happens on the ProviderDocumentReview list page below.
    """
    model = ProviderDocumentReview
    extra = 0
    fields = ("field_name", "status", "thumbnail", "rejection_category", "rejection_reason", "updated_at")
    readonly_fields = ("field_name", "thumbnail", "updated_at")
    can_delete = False

    def thumbnail(self, obj):
        if obj.document_url:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:80px;border-radius:4px;"/></a>',
                obj.document_url,
            )
        return "—"
    thumbnail.short_description = "Preview"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HealthcareProvider)
class HealthcareProviderAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "speciality", "profile_complete",
        "pending_documents_count", "rejected_documents_count",
    )
    list_filter = ("profile_complete", "speciality")
    search_fields = (
        "identity__first_name", "identity__last_name", "identity__email",
    )
    inlines = [ProviderDocumentReviewInline]

    def pending_documents_count(self, obj):
        return obj.document_reviews.filter(status=ProviderDocumentReview.STATUS_PENDING).count()
    pending_documents_count.short_description = "Pending docs"

    def rejected_documents_count(self, obj):
        return obj.document_reviews.filter(status=ProviderDocumentReview.STATUS_REJECTED).count()
    rejected_documents_count.short_description = "Rejected docs"


@admin.register(ProviderDocumentReview)
class ProviderDocumentReviewAdmin(admin.ModelAdmin):
    """
    The main review queue. Filter by status/field, click into a row to
    approve or reject with a category + specific written reason, or
    select multiple rows and use the bulk actions for quick sweeps.
    """
    list_display = (
        "provider_name", "field_name", "status", "thumbnail",
        "rejection_category", "rejection_reason", "updated_at",
    )
    list_filter = ("status", "field_name", "rejection_category")
    search_fields = (
        "provider__identity__first_name",
        "provider__identity__last_name",
        "provider__identity__email",
    )
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

    def large_preview(self, obj):
        if obj.document_url:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:500px;border-radius:6px;"/></a>',
                obj.document_url,
            )
        return "No document uploaded"
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
