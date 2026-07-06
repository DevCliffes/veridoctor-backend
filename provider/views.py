import os
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

ALLOWED_DOCUMENT_FIELDS = [
    "national_id_image",
    "clinic_logo_url",
    "business_reg_image",
    "operating_licence_image",
    "kra_pin_image",
    "cr12_image",
    "valid_licence_image",
]


# ─────────────────────────────────────────────────────────────────────────
# SCHEDULE OVERLAP DETECTION
#
# Recurring schedules can share overlapping date ranges without ever
# occurring on the same actual day (e.g. Mon/Wed/Fri vs Tue/Thu), so a naive
# "do these date ranges intersect" check would produce false positives and
# false negatives. Instead we expand both schedules day-by-day (bounded to
# a fixed window) and check whether they land on the same calendar date
# with overlapping times -- mirroring expandToCalendarEvents() in the
# frontend's Schedule.tsx exactly, so what gets rejected here matches what
# would actually render as a conflict on the calendar.
#
# Booked appointments are deliberately NOT part of this check. By design,
# a booked appointment occupies a slot that was carved out of an existing
# ProviderSchedule block (see ProviderAvailableSlotsView), and the calendar
# UI already renders bookings as overriding their parent schedule slot.
# As long as no two ProviderSchedule blocks are ever allowed to overlap,
# there is structurally no room for two open slots -- and therefore no
# room for two bookings -- to ever occupy the same time. Enforcing
# non-overlap at the schedule layer is sufficient and is the single
# source of truth; a separate booking-vs-booking check would be redundant
# as long as this function has no gaps.
# ─────────────────────────────────────────────────────────────────────────

# recurrence_days is stored using JS's Date.getDay() convention
# (Sunday=0..Saturday=6) -- see DAY_ABBR in Schedule.tsx -- NOT Python's
# date.weekday() convention (Monday=0..Sunday=6).
DOW_ABBR_JS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

# Recurring "never-ending" schedules are stored with a sentinel end_date of
# 2099-12-31 (see the overrides in ProviderScheduleView.post and
# ProviderScheduleDetailView.patch). Expanding a recurrence out that far to
# check for overlaps isn't useful in practice, so detection is bounded to
# this many days from today.
MAX_OVERLAP_CHECK_DAYS = 730


def _js_dow_abbr(day):
    return DOW_ABBR_JS[(day.weekday() + 1) % 7]


def _schedule_occurs_on(spec, day):
    if day < spec["start_date"] or day > spec["end_date"]:
        return False
    if day.isoformat() in (spec["excluded_dates"] or []):
        return False
    recurrence = spec["recurrence"]
    if recurrence == "none":
        return day == spec["start_date"]
    if recurrence == "daily":
        return True
    if recurrence == "weekdays":
        return day.weekday() < 5
    if recurrence in ("weekly", "custom"):
        if _js_dow_abbr(day) not in (spec["recurrence_days"] or []):
            return False
        # FIX: previously any matching weekday was treated as an occurrence,
        # regardless of recurrence_interval. That meant e.g. two "every 2
        # weeks on Mon" schedules starting on different offset weeks were
        # flagged as conflicting even though they never actually land on
        # the same date (false positive), while the converse case -- two
        # interval-based schedules whose occurrences DO align -- could only
        # be caught by accident, since interval never factored into the
        # comparison at all. Determine which week `day` falls in relative
        # to the schedule's own start_date, and only treat it as occurring
        # every Nth such week.
        interval = spec.get("recurrence_interval") or 1
        if interval <= 1:
            return True
        start_week_monday = spec["start_date"] - timedelta(
            days=spec["start_date"].weekday()
        )
        day_week_monday = day - timedelta(days=day.weekday())
        weeks_elapsed = (day_week_monday - start_week_monday).days // 7
        return weeks_elapsed % interval == 0
    return False


def _find_conflicting_date(new_spec, existing_spec, window_start, window_end):
    """
    Returns the first calendar date on which both schedule specs occur AND
    their times overlap, or None if they never conflict within the window.
    """
    if not (
        new_spec["start_time"] < existing_spec["end_time"]
        and new_spec["end_time"] > existing_spec["start_time"]
    ):
        return None

    range_start = max(new_spec["start_date"], existing_spec["start_date"], window_start)
    range_end = min(new_spec["end_date"], existing_spec["end_date"], window_end)
    if range_start > range_end:
        return None

    cursor = range_start
    while cursor <= range_end:
        if _schedule_occurs_on(new_spec, cursor) and _schedule_occurs_on(existing_spec, cursor):
            return cursor
        cursor += timedelta(days=1)
    return None


def _spec_from_schedule(schedule):
    return {
        "start_date": schedule.start_date,
        "end_date": schedule.end_date,
        "start_time": schedule.start_time,
        "end_time": schedule.end_time,
        "recurrence": schedule.recurrence,
        "recurrence_days": schedule.recurrence_days,
        "recurrence_interval": schedule.recurrence_interval,
        "excluded_dates": schedule.excluded_dates,
    }


def _spec_from_data(data):
    return {
        "start_date": data["start_date"],
        "end_date": data["end_date"],
        "start_time": data["start_time"],
        "end_time": data["end_time"],
        "recurrence": data.get("recurrence", "none"),
        "recurrence_days": data.get("recurrence_days", []) or [],
        "recurrence_interval": data.get("recurrence_interval", 1) or 1,
        "excluded_dates": data.get("excluded_dates", []) or [],
    }


def _check_schedule_overlap(provider, new_spec, exclude_schedule_id=None):
    """
    Checks new_spec against every other ProviderSchedule for this provider.
    Returns a Response(409) describing the conflict if one is found,
    otherwise None.
    """
    window_start = date.today()
    window_end = window_start + timedelta(days=MAX_OVERLAP_CHECK_DAYS)

    existing_qs = ProviderSchedule.objects.filter(provider=provider)
    if exclude_schedule_id:
        existing_qs = existing_qs.exclude(id=exclude_schedule_id)

    for existing in existing_qs:
        conflict_date = _find_conflicting_date(
            new_spec, _spec_from_schedule(existing), window_start, window_end
        )
        if conflict_date:
            existing_label = existing.service.name if existing.service else "an existing block"
            return Response(
                {
                    "error": (
                        f'This time slot overlaps with "{existing_label}" '
                        f"on {conflict_date.isoformat()}."
                    ),
                    "conflict_date": conflict_date.isoformat(),
                    "conflicting_schedule_id": str(existing.id),
                },
                status=status.HTTP_409_CONFLICT,
            )
    return None


class ProviderProfileView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)

        provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)

        return Response({
            "first_name": identity.first_name,
            "last_name": identity.last_name,
            "email": identity.email,
            "title": provider.title or "Dr.",
            "speciality": provider.speciality or "",
            "subspecialties": provider.subspecialties or [],
            "phone_number": provider.phone_number or identity.phone_number or "",
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
            "national_id_number": getattr(provider, "national_id_number", "") or "",
            "national_id_image": getattr(provider, "national_id_image", "") or "",
            "clinic_logo_url": getattr(provider, "clinic_logo_url", "") or "",
            "business_reg_number": getattr(provider, "business_reg_number", "") or "",
            "business_reg_image": getattr(provider, "business_reg_image", "") or "",
            "operating_licence": getattr(provider, "operating_licence", "") or "",
            "operating_licence_image": getattr(provider, "operating_licence_image", "") or "",
            "kra_pin": getattr(provider, "kra_pin", "") or "",
            "kra_pin_image": getattr(provider, "kra_pin_image", "") or "",
            "cr12_image": getattr(provider, "cr12_image", "") or "",
            "valid_licence_number": getattr(provider, "valid_licence_number", "") or "",
            "valid_licence_image": getattr(provider, "valid_licence_image", "") or "",
            "extra_credentials": getattr(provider, "extra_credentials", []) or [],
        })

    def patch(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)

        provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)

        for field in ["first_name", "last_name"]:
            if field in request.data:
                setattr(identity, field, request.data[field])
        identity.save()

        for field in [
            "speciality", "subspecialties", "phone_number", "licence_number", "licence_type",
            "title", "clinic_name", "address", "county", "country",
            "bio", "insurances_accepted", "languages", "profile_picture_url",
            "national_id_number", "national_id_image",
            "clinic_logo_url",
            "business_reg_number", "business_reg_image",
            "operating_licence", "operating_licence_image",
            "kra_pin", "kra_pin_image",
            "cr12_image",
            "valid_licence_number", "valid_licence_image",
            "extra_credentials",
        ]:
            if field in request.data:
                setattr(provider, field, request.data[field])
        provider.save()

        return Response({"success": True})


class ProviderDocumentUploadView(APIView):
    def post(self, request, identity_id):
        import cloudinary
        import cloudinary.uploader

        field_name = request.query_params.get("field")
        if not field_name or field_name not in ALLOWED_DOCUMENT_FIELDS:
            return Response(
                {"error": f"Invalid field. Allowed: {', '.join(ALLOWED_DOCUMENT_FIELDS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            identity = Identity.objects.get(id=identity_id)
            provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
        except Identity.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
        api_key = os.environ.get("CLOUDINARY_API_KEY")
        api_secret = os.environ.get("CLOUDINARY_API_SECRET")

        if not all([cloud_name, api_key, api_secret]):
            return Response({"error": "Cloudinary not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)

        try:
            result = cloudinary.uploader.upload(
                file,
                folder=f"veridoctor/providers/{identity_id}",
                public_id=field_name,
                overwrite=True,
                resource_type="auto",
            )
        except Exception as e:
            return Response({"error": f"Upload failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        url = result.get("secure_url")
        if not url:
            return Response({"error": "No URL returned from Cloudinary"}, status=status.HTTP_502_BAD_GATEWAY)

        setattr(provider, field_name, url)
        provider.save(update_fields=[field_name])

        return Response({"url": url}, status=status.HTTP_200_OK)


class ProviderGenericImageUploadView(APIView):
    def post(self, request, identity_id):
        import cloudinary
        import cloudinary.uploader
        import uuid

        try:
            Identity.objects.get(id=identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
        api_key = os.environ.get("CLOUDINARY_API_KEY")
        api_secret = os.environ.get("CLOUDINARY_API_SECRET")

        if not all([cloud_name, api_key, api_secret]):
            return Response({"error": "Cloudinary not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)

        label = request.query_params.get("label", str(uuid.uuid4())[:8])
        try:
            result = cloudinary.uploader.upload(
                file,
                folder=f"veridoctor/providers/{identity_id}",
                public_id=f"cred_{label}",
                overwrite=True,
                resource_type="image",
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        url = result.get("secure_url")
        if not url:
            return Response({"error": "No URL returned"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"url": url}, status=status.HTTP_200_OK)


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

            patient_email = request.data.get("patient_email", "")
            patient_name = request.data.get("patient_name", "")
            raw_patient_id = request.data.get("patient_id", "")

            patient_identity = None
            if raw_patient_id:
                try:
                    patient_identity = Identity.objects.get(id=raw_patient_id)
                except (Identity.DoesNotExist, ValueError):
                    patient_identity = None
            if not patient_identity and patient_email:
                patient_identity = find_identity_by_email(patient_email)

            prescription = Prescription.objects.create(
                provider=provider,
                patient_id=raw_patient_id,
                patient_name=patient_name,
                patient_email=patient_email,
                patient_identity=patient_identity,
                diagnosis=request.data.get("diagnosis", ""),
                notes=request.data.get("notes", ""),
            )

            # TEMP DEBUG: wrap each drug creation so any failure is visible in the
            # API response itself, instead of a silent/opaque 500. Remove once fixed.
            drugs_data = request.data.get("drugs", [])
            drug_errors = []
            for i, drug in enumerate(drugs_data):
                try:
                    PrescriptionDrug.objects.create(
                        prescription=prescription,
                        drug_name=str(drug.get("drug_name") or drug.get("name") or "").strip(),
                        dosage=str(drug.get("dosage") or "").strip(),
                        frequency=str(drug.get("frequency") or "").strip(),
                        duration=str(drug.get("duration") or "").strip(),
                        instructions=str(drug.get("instructions") or "").strip(),
                    )
                except Exception as drug_exc:
                    drug_errors.append({
                        "index": i,
                        "raw_drug": drug,
                        "error": str(drug_exc),
                        "error_type": type(drug_exc).__name__,
                    })

            if drug_errors:
                # Prescription saved, but one or more drug rows failed.
                # Return 200 with the failure details visible in the response body.
                serializer = PrescriptionSerializer(prescription)
                return Response(
                    {
                        **serializer.data,
                        "_debug_drug_errors": drug_errors,
                    },
                    status=status.HTTP_200_OK,
                )

            if patient_identity:
                refresh_record_summary(patient_identity, provider)

            serializer = PrescriptionSerializer(prescription)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # TEMP DEBUG: surface any other exception directly in the response body
            # so the traceback is visible in DevTools Network -> Response, without
            # needing access to Render logs. Remove once fixed.
            import traceback
            return Response(
                {
                    "error": "Unhandled exception in PrescriptionView.post",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc(),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
            return Response(
                {"error": "patient_email query param required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prescriptions = Prescription.objects.filter(
            patient_email=patient_email
        ).order_by("-created_at")
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
            new_spec = _spec_from_data(serializer.validated_data)
            conflict_response = _check_schedule_overlap(provider, new_spec)
            if conflict_response:
                return conflict_response
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
            # PATCH is partial, so build the full resulting spec (existing
            # fields overlaid with the incoming changes) for overlap
            # checking rather than relying on validated_data alone, which
            # may omit fields the request didn't touch.
            merged = _spec_from_schedule(schedule)
            merged.update(serializer.validated_data)
            new_spec = _spec_from_data(merged)
            conflict_response = _check_schedule_overlap(
                schedule.provider, new_spec, exclude_schedule_id=schedule.id
            )
            if conflict_response:
                return conflict_response
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
            if not p.profile_complete:
                continue  # not bookable until profile is complete
            services = list(p.services.filter(price_visible=True).values(
                "id", "name", "price", "currency", "estimated_duration"
            ))
            data.append({
                "id": str(p.identity.id),
                "first_name": p.identity.first_name,
                "last_name": p.identity.last_name,
                "title": p.title or "Dr.",
                "speciality": p.speciality,
                "subspecialties": p.subspecialties or [],
                "clinic_name": p.clinic_name or "",
                "county": p.county or "",
                "bio": p.bio or "",
                "languages": p.languages or [],
                "insurances_accepted": p.insurances_accepted or [],
                "profile_picture_url": p.profile_picture_url or "",
                "clinic_logo_url": getattr(p, "clinic_logo_url", "") or "",
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
            "subspecialties": provider.subspecialties or [],
            "clinic_name": provider.clinic_name or "",
            "address": provider.address or "",
            "county": provider.county or "",
            "country": provider.country or "Kenya",
            "bio": provider.bio or "",
            "languages": provider.languages or [],
            "insurances_accepted": provider.insurances_accepted or [],
            "profile_picture_url": provider.profile_picture_url or "",
            "clinic_logo_url": getattr(provider, "clinic_logo_url", "") or "",
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

        insurances = []
        try:
            from identity.models import patientAccount
            account = patientAccount.objects.filter(identity=patient_identity).first()
            if account:
                insurances = getattr(account, "insurances", []) or []
        except Exception:
            pass

        return Response({
            "phone_number": patient_identity.phone_number or "",
            "first_name": patient_identity.first_name,
            "last_name": patient_identity.last_name,
            "email": patient_identity.email,
            "insurances": insurances,
        })


class ProviderPhotoUploadView(APIView):
    def post(self, request, identity_id):
        import cloudinary
        import cloudinary.uploader

        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        photo = request.FILES.get("photo")
        if not photo:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
        api_key = os.environ.get("CLOUDINARY_API_KEY")
        api_secret = os.environ.get("CLOUDINARY_API_SECRET")

        if not all([cloud_name, api_key, api_secret]):
            return Response({"error": "Cloudinary not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)

        try:
            result = cloudinary.uploader.upload(
                photo,
                folder=f"veridoctor/providers/{identity_id}",
                public_id="profile_photo",
                overwrite=True,
                resource_type="image",
            )
        except Exception as e:
            return Response({"error": f"Upload failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        secure_url = result.get("secure_url")
        if not secure_url:
            return Response({"error": "No URL returned"}, status=status.HTTP_502_BAD_GATEWAY)

        provider.profile_picture_url = secure_url
        provider.save(update_fields=["profile_picture_url"])

        return Response({"profile_picture_url": secure_url}, status=status.HTTP_200_OK)
