"""
URL configuration for config project.
"""

from django.urls import path
from .views import FacilityView

urlpatterns = [
    path("", FacilityView.as_view(), name="facility-list-create"),
    # path("list/", FacilityListView.as_view(), name="facility-list"),
    # path("detail/<int:pk>/", FacilityDetailView.as_view(), name="facility-detail"),
]
