from .models import (
    HealthcareProvider,
    Service,
    Form,
    Prescription,
    PrescriptionDrug,
    ProviderSchedule,
)
from .serializers import (
    ServiceSerializer,
    FormSerializer,
    PrescriptionSerializer,
    ProviderScheduleSerializer,
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from identity.models import Identity
from datetime import date, datetime, timedelta
from django.utils import timezone as dj_timezone
from appointments.models import ProviderAppointment
from records.services import find_identity_by_email, refresh_record_summary


class ProviderProfileView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "first_name": identity.first_name,
            "last_name": identity.last_name,
            "email": identity.email,
            "title": provider.title or "Dr.",
            "speciality": provider.speciality or "",
            "phone_number": provider.phone_number or "",
            "licence_number": provider.licence_number or "",
            "licence_type": provider.licence_type or "",
            "clinic_name": provider.clinic_name or "",
            "address": provider.address or "",
            "county": provider.county or "",
            "country": provider.country or "Kenya",
            "bio": provider.bio or "",
            "insurances_accepted": provider.insurances_accepted or [],
            "languages": provider.languages or ["English"],
            "profile_picture_url": provider.profile_picture_url or "",
        })

    def patch(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        for field in ["first_name", "last_name"]:
            if field in request.data:
                setattr(identity, field, request.data[field])
        identity.save()

        for field in [
            "speciality", "phone_number", "licence_number", "licence_type",
            "title", "clinic_name", "address", "county", "country",
            "bio", "insurances_accepted", "languages", "profile_picture_url",
        ]:
            if field in request.data:
                setattr(provider, field, request.data[field])
        provider.save()

        return Response({"success": True})


class ServiceView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
            services = Service.objects.filter(provider=provider)
            serializer = ServiceSerializer(services, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
            serializer = ServiceSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(provider=provider)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)


class ServiceDetailView(APIView):
    def patch(self, request, identity_id, service_id):
        try:
            service = Service.objects.get(id=service_id)
            serializer = ServiceSerializer(service, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Service.DoesNotExist:
            return Response({"error": "Service not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, identity_id, service_id):
        try:
            service = Service.objects.get(id=service_id)
            service.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Service.DoesNotExist:
            return Response({"error": "Service not found"}, status=status.HTTP_404_NOT_FOUND)


class FormView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
            forms = Form.objects.filter(provider=provider)
            serializer = FormSerializer(forms, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
            serializer = FormSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(provider=provider)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)


class FormDetailView(APIView):
    def get(self, request, identity_id, form_id):
        try:
            form = Form.objects.get(id=form_id)
            serializer = FormSerializer(form)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Form.DoesNotExist:
            return Response({"error": "Form not found"}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, identity_id, form_id):
        try:
            form = Form.objects.get(id=form_id)
            serializer = FormSerializer(form, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Form.DoesNotExist:
            return Response({"error": "Form not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, identity_id, form_id):
        try:
            form = Form.objects.get(id=form_id)
            form.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Form.DoesNotExist:
            return Response({"error": "Form not found"}, status=status.HTTP_404_NOT_FOUND)


class PrescriptionView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
            prescriptions = Prescription.objects.filter(provider=provider).order_by("-created_at")
            serializer = PrescriptionSerializer(prescriptions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
            patient_identity = find_identity_by_email(request.data.get("patient_email"))
            prescription = Prescription.objects.create(
                provider=provider,
                patient_id=request.data.get("patient_id", ""),
                patient_name=request.data.get("patient_name", ""),
                patient_email=request.data.get("patient_email", ""),
                patient_identity=patient_identity,
                diagnosis=request.data.get("diagnosis", ""),
                notes=request.data.get("notes", ""),
            )
            for drug in request.data.get("drugs", []):
                PrescriptionDrug.objects.create(
                    prescription=prescription,
                    drug_name=drug.get("drug_name", ""),
                    dosage=drug.get("dosage", ""),
                    frequency=drug.get("frequency", ""),
                    duration=drug.get("duration", ""),
                    instructions=drug.get("instructions", ""),
                )
            refresh_record_summary(patient_identity, provider)
            serializer = PrescriptionSerializer(prescription)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)


class PrescriptionDetailView(APIView):
    def get(self, request, identity_id, prescription_id):
        try:
            prescription = Prescription.objects.get(id=prescription_id)
            serializer = PrescriptionSerializer(prescription)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Prescription.DoesNotExist:
            return Response({"error": "Prescription not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, identity_id, prescription_id):
        try:
            prescription = Prescription.objects.get(id=prescription_id)
            prescription.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Prescription.DoesNotExist:
            return Response({"error": "Prescription not found"}, status=status.HTTP_404_NOT_FOUND)


class PatientPrescriptionView(APIView):
    def get(self, request):
        patient_email = request.query_params.get("patient_email")
        if not patient_email:
            return Response({"error": "patient_email query param required"}, status=status.HTTP_400_BAD_REQUEST)
        prescriptions = Prescription.objects.filter(patient_email=patient_email).order_by("-created_at")
        serializer = PrescriptionSerializer(prescriptions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProviderScheduleView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
        schedules = ProviderSchedule.objects.filter(provider=provider).order_by("start_date", "start_time")
        serializer = ProviderScheduleSerializer(schedules, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        if (
            data.get("recurrence", "none") != "none"
            and data.get("recurrence_end_type") in (None, "never", "")
        ):
            data["end_date"] = "2099-12-31"
        serializer = ProviderScheduleSerializer(data=data)
        if serializer.is_valid():
            serializer.save(provider=provider)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProviderScheduleDetailView(APIView):
    def patch(self, request, identity_id, schedule_id):
        try:
            schedule = ProviderSchedule.objects.get(id=schedule_id)
        except ProviderSchedule.DoesNotExist:
            return Response({"error": "Schedule not found"}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        effective_recurrence = data.get("recurrence", schedule.recurrence)
        effective_end_type = data.get("recurrence_end_type", schedule.recurrence_end_type)
        if effective_recurrence != "none" and effective_end_type in (None, "never", ""):
            data["end_date"] = "2099-12-31"
        serializer = ProviderScheduleSerializer(schedule, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, identity_id, schedule_id):
        try:
            schedule = ProviderSchedule.objects.get(id=schedule_id)
        except ProviderSchedule.DoesNotExist:
            return Response({"error": "Schedule not found"}, status=status.HTTP_404_NOT_FOUND)
        occurrence_date = request.query_params.get("occurrence_date")
        delete_series = request.query_params.get("delete_series") == "true"
        if schedule.recurrence != "none" and occurrence_date and not delete_series:
            excluded = schedule.excluded_dates or []
            if occurrence_date not in excluded:
                excluded.append(occurrence_date)
            schedule.excluded_dates = excluded
            schedule.save(update_fields=["excluded_dates"])
            return Response(ProviderScheduleSerializer(schedule).data, status=status.HTTP_200_OK)
        schedule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProviderListView(APIView):
    def get(self, request):
        speciality = request.query_params.get("speciality", "")
        providers = HealthcareProvider.objects.select_related("identity").prefetch_related("services")
        if speciality:
            providers = providers.filter(speciality__icontains=speciality)
        data = []
        for p in providers:
            services = list(p.services.filter(price_visible=True).values(
                "id", "name", "price", "currency", "estimated_duration"
            ))
            data.append({
                "id": str(p.identity.id),
                "first_name": p.identity.first_name,
                "last_name": p.identity.last_name,
                "speciality": p.speciality,
                "clinic_name": p.clinic_name or "",
                "county": p.county or "",
                "bio": p.bio or "",
                "languages": p.languages or [],
                "insurances_accepted": p.insurances_accepted or [],
                "profile_picture_url": p.profile_picture_url or "",
                "services": services,
            })
        return Response(data)


class ProviderPublicProfileView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.select_related("identity").get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
        services = list(
            provider.services.filter(price_visible=True).values(
                "id", "name", "price", "currency", "estimated_duration", "description"
            )
        )
        return Response({
            "id": str(identity.id),
            "first_name": identity.first_name,
            "last_name": identity.last_name,
            "title": provider.title or "Dr.",
            "speciality": provider.speciality or "",
            "clinic_name": provider.clinic_name or "",
            "address": provider.address or "",
            "county": provider.county or "",
            "country": provider.country or "Kenya",
            "bio": provider.bio or "",
            "languages": provider.languages or [],
            "insurances_accepted": provider.insurances_accepted or [],
            "profile_picture_url": provider.profile_picture_url or "",
            "services": services,
        })


class ProviderAvailableSlotsView(APIView):
    def get(self, request, identity_id):
        query_date_str = request.query_params.get("date")
        if not query_date_str:
            return Response({"error": "date param required (YYYY-MM-DD)"}, status=400)
        try:
            query_date = date.fromisoformat(query_date_str)
        except ValueError:
            return Response({"error": "Invalid date format"}, status=400)
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=404)

        python_dow = query_date.weekday()
        dow_abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][python_dow]
        query_date_str_iso = query_date.isoformat()

        schedules = ProviderSchedule.objects.filter(
            provider=provider,
            start_date__lte=query_date,
            end_date__gte=query_date,
        )

        matching = []
        for s in schedules:
            if query_date_str_iso in (s.excluded_dates or []):
                continue
            r = s.recurrence
            if r == "none" and s.start_date == query_date:
                matching.append(s)
            elif r == "daily":
                matching.append(s)
            elif r == "weekdays" and python_dow < 5:
                matching.append(s)
            elif r in ("weekly", "custom") and dow_abbr in (s.recurrence_days or []):
                matching.append(s)

        booked_qs = ProviderAppointment.objects.filter(
            provider=provider,
            start_time__date=query_date,
            status__in=["scheduled", "confirmed", "in-progress"],
        ).values_list("start_time", "end_time")

        local_tz = dj_timezone.get_current_timezone()
        booked_ranges = []
        for utc_start, utc_end in booked_qs:
            local_start = utc_start.astimezone(local_tz).replace(tzinfo=None)
            local_end = utc_end.astimezone(local_tz).replace(tzinfo=None)
            booked_ranges.append((local_start, local_end))

        slots = []
        seen = set()
        for s in matching:
            start_dt = datetime.combine(query_date, s.start_time)
            end_dt = datetime.combine(query_date, s.end_time)
            duration = s.service.estimated_duration if s.service else 30
            cursor = start_dt
            while cursor + timedelta(minutes=duration) <= end_dt:
                slot_end = cursor + timedelta(minutes=duration)
                key = cursor.isoformat()
                if key not in seen:
                    overlaps = any(
                        not (slot_end <= bs or cursor >= be)
                        for bs, be in booked_ranges
                    )
                    if not overlaps:
                        slots.append({
                            "start_time": cursor.isoformat(),
                            "end_time": slot_end.isoformat(),
                            "service_id": str(s.service.id) if s.service else None,
                            "service_name": s.service.name if s.service else None,
                            "location_type": s.location_type,
                            "duration_minutes": duration,
                        })
                    seen.add(key)
                cursor += timedelta(minutes=duration)

        return Response(slots)


class PatientDetailView(APIView):
    def get(self, request, identity_id, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "phone_number": patient_identity.phone_number or "",
            "first_name": patient_identity.first_name,
            "last_name": patient_identity.last_name,
            "email": patient_identity.email,
        })


class ProviderPhotoUploadView(APIView):
    """
    Accepts a multipart image upload from the provider profile page,
    pushes it to Cloudinary, and saves the returned secure URL onto
    the provider's profile_picture_url field.

    POST /provider/<identity_id>/photo
    Body: multipart/form-data with a "photo" file field.

    Requires these environment variables to be set on the backend:
      CLOUDINARY_CLOUD_NAME
      CLOUDINARY_API_KEY
      CLOUDINARY_API_SECRET
    """
    def post(self, request, identity_id):
        import os
        import cloudinary
        import cloudinary.uploader

        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        photo = request.FILES.get("photo")
        if not photo:
            return Response(
                {"error": "No file provided. Send multipart/form-data with a 'photo' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
        api_key = os.environ.get("CLOUDINARY_API_KEY")
        api_secret = os.environ.get("CLOUDINARY_API_SECRET")

        if not all([cloud_name, api_key, api_secret]):
            return Response(
                {"error": "Cloudinary is not configured on the server. "
                          "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, "
                          "CLOUDINARY_API_SECRET environment variables."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )

        try:
            result = cloudinary.uploader.upload(
                photo,
                folder="veridoctor/provider_photos",
                public_id=f"provider_{identity_id}",
                overwrite=True,
                resource_type="image",
            )
        except Exception as e:
            return Response(
                {"error": f"Upload to Cloudinary failed: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        secure_url = result.get("secure_url")
        if not secure_url:
            return Response(
                {"error": "Cloudinary did not return a URL"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        provider.profile_picture_url = secure_url
        provider.save(update_fields=["profile_picture_url"])

        return Response({"profile_picture_url": secure_url}, status=status.HTTP_200_OK)


class ProviderPhotoView(APIView):
    """
    DEAD CODE — unreachable. ProviderPhotoUploadView is registered first
    in urls.py for the same path ("<str:identity_id>/photo"), so Django
    always matches that one. Kept here only because removing it isn't
    required for correctness; safe to delete in a future cleanup pass.

    Handles profile photo upload for a provider.
    POST /provider/<identity_id>/photo
    Accepts multipart/form-data with a 'photo' field.
    Stores the image as base64 data URL (no external storage needed).
    """
    def post(self, request, identity_id):
        import base64

        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        photo = request.FILES.get("photo")
        if not photo:
            return Response({"error": "No photo file provided"}, status=status.HTTP_400_BAD_REQUEST)

        allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
        if photo.content_type not in allowed_types:
            return Response(
                {"error": "Invalid file type. Use JPEG, PNG, WebP, or GIF."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if photo.size > 5 * 1024 * 1024:
            return Response(
                {"error": "File too large. Maximum size is 5MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        photo_data = base64.b64encode(photo.read()).decode("utf-8")
        data_url = f"data:{photo.content_type};base64,{photo_data}"

        provider.profile_picture_url = data_url
        provider.save(update_fields=["profile_picture_url"])

        return Response(
            {"profile_picture_url": data_url},
            status=status.HTTP_200_OK,
        )
