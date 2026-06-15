class ProviderDashboardStatsView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        today = now.astimezone(timezone.get_current_timezone()).date()

        # This week Mon–Sun in local time
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        # This month
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        base_qs = ProviderAppointment.objects.filter(provider=provider)

        # Today — use __date= which respects USE_TZ correctly
        today_qs = base_qs.filter(start_time__date=today)
        today_count = today_qs.count()

        # This week
        week_qs = base_qs.filter(start_time__gte=week_start, start_time__lt=week_end)
        this_week_appointments = week_qs.count()
        this_week_patients = week_qs.values("patient_email").distinct().count()

        # Monthly distinct patients
        month_qs = base_qs.filter(start_time__gte=month_start)
        total_patients_month = month_qs.values("patient_email").distinct().count()

        # Average duration (minutes) this month — exclude cancelled
        month_with_duration = month_qs.exclude(status="cancelled").annotate(
            duration=ExpressionWrapper(
                F("end_time") - F("start_time"), output_field=DurationField()
            )
        )
        avg_duration_td = month_with_duration.aggregate(avg=Avg("duration"))["avg"]
        avg_duration_minutes = int(avg_duration_td.total_seconds() / 60) if avg_duration_td else 0

        # Weekly chart — last 7 days
        weekly_data = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).astimezone(
                timezone.get_current_timezone()
            ).date()
            count = base_qs.filter(start_time__date=day).count()
            weekly_data.append({
                "date": day.isoformat(),
                "day": day.strftime("%a"),
                "count": count,
            })

        # Upcoming today (not yet started, not cancelled)
        upcoming_today = today_qs.filter(
            start_time__gt=now,
            status__in=["scheduled", "confirmed"]
        ).count()

        # Pending (scheduled but not confirmed)
        pending_count = base_qs.filter(status="scheduled").count()

        return Response({
            "today_count": today_count,
            "upcoming_today": upcoming_today,
            "pending_count": pending_count,
            "this_week_appointments": this_week_appointments,
            "this_week_patients": this_week_patients,
            "total_patients_month": total_patients_month,
            "avg_duration_minutes": avg_duration_minutes,
            "weekly_data": weekly_data,
        })
