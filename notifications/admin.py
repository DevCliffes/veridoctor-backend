from django.contrib import admin
from .models import Notification, PushSubscription, AppointmentReminderLog


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "identity", "endpoint", "created_at")
    list_filter = ("created_at",)
    search_fields = ("identity__email", "endpoint")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient_identity", "notification_type", "title", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "recipient_identity__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AppointmentReminderLog)
class AppointmentReminderLogAdmin(admin.ModelAdmin):
    list_display = ("id", "appointment", "reminder_type", "sent_at")
    list_filter = ("reminder_type", "sent_at")
