class ProviderPatientRelationshipRequired(BasePermission):
    """
    Provider-side equivalent of RecordsUnlockRequired.

    FIX: previously did not check request.user at all -- it only verified
    that the provider_id/patient_identity_id pair in the URL had a real,
    non-cancelled appointment between them, regardless of who the caller
    actually was. That meant anyone who could guess or enumerate a valid
    (provider_id, patient_identity_id) pair -- authenticated or not --
    could pass this check without being that provider. This was written
    that way because, at the time, apps/provider did not attach an
    Authorization header, so requiring request.user would have rejected
    every legitimate request. apps/provider (served from
    provider.veridoctor.com) now attaches a Bearer token via
    maybeAuthoriseProvider() in axios-client.ts on every non-public
    request, so request.user is reliably populated and can be checked.

    Access is granted only if:
      1. The caller is authenticated, AND
      2. The caller IS the provider identified by the `provider_id` URL
         kwarg, AND
      3. That provider has at least one non-cancelled ProviderAppointment
         with the patient identified by `patient_identity_id`.
    """
    message = "No existing care relationship found with this patient."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        provider_identity_id = view.kwargs.get("provider_id")
        patient_identity_id = view.kwargs.get("patient_identity_id")
        if not provider_identity_id or not patient_identity_id:
            return False

        # The caller must actually BE the provider named in the URL.
        if str(request.user.id) != str(provider_identity_id):
            return False

        from provider.models import HealthcareProvider
        from appointments.models import ProviderAppointment

        try:
            provider = HealthcareProvider.objects.get(identity__id=provider_identity_id)
        except HealthcareProvider.DoesNotExist:
            return False

        return (
            ProviderAppointment.objects.filter(
                provider=provider,
                patient_identity__id=patient_identity_id,
            )
            .exclude(status="cancelled")
            .exists()
        )
