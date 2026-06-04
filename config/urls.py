"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("identity/", include("identity.urls")),
    path("facility/", include("facility.urls")),
]
