"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse


def health_check(request):
    return HttpResponse("OK")


urlpatterns = [
    path("health/", health_check),
    path("admin/", admin.site.urls),
    path("identity/", include("identity.urls")),
    path("facility/", include("facility.urls")),
    path("provider/", include("provider.urls")),
    path("records/", include("records.urls")),
    path("appointments/", include("appointments.urls")),
    path("notifications/", include("notifications.urls")),
]
