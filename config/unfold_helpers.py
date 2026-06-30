"""
Helper callbacks for django-unfold admin customization.
Referenced from settings.py UNFOLD config.
"""
def environment_callback(request):
    """
    Shows a small colored badge in the admin header indicating
    which environment you're looking at.
    """
    import os
    if os.getenv("DJANGO_DEBUG_MODE", "True") == "True":
        return ["Development", "warning"]
    return ["Production", "danger"]


def dashboard_callback(request, context):
    """
    Injects custom data into the admin index page context.
    Pulls quick counts so the dashboard home page shows something
    useful at a glance instead of being blank.
    """
    from appointments.models import ProviderAppointment
    from identity.models import patientAccount, HealthcareProviderAccount
    from providers.models import HealthcareProvider

    incomplete_count = HealthcareProvider.objects.filter(profile_complete=False).count()

    context.update(
        {
            "kpi": [
                {
                    "title": "Total Patients",
                    "metric": patientAccount.objects.count(),
                    "icon": "person",
                },
                {
                    "title": "Total Providers",
                    "metric": HealthcareProviderAccount.objects.count(),
                    "icon": "medical_services",
                },
                {
                    "title": "Total Appointments",
                    "metric": ProviderAppointment.objects.count(),
                    "icon": "event",
                },
                {
                    "title": "Incomplete Profiles",
                    "metric": incomplete_count,
                    "icon": "warning",
                    "link": "/admin/providers/healthcareprovider/?profile_complete__exact=0",
                },
            ],
        }
    )
    return context
