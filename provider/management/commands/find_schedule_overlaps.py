"""
One-off audit script to find ProviderSchedule blocks that overlap each
other -- i.e. data that predates the overlap-prevention check being added
to ProviderScheduleView.post / ProviderScheduleDetailView.patch, or that
slipped through before the recurrence_interval fix.

Reuses _schedule_occurs_on / _find_conflicting_date / _spec_from_schedule
directly from provider.views so the definition of "overlap" here is
identical to what the live API now enforces -- this only reports existing
conflicts, it does not modify any data.

Usage:
    python manage.py find_schedule_overlaps
    python manage.py find_schedule_overlaps --provider <identity_id>
    python manage.py find_schedule_overlaps --days 365
"""

from collections import defaultdict
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from provider.models import HealthcareProvider, ProviderSchedule
from provider.views import (
    MAX_OVERLAP_CHECK_DAYS,
    _find_conflicting_date,
    _spec_from_schedule,
)


class Command(BaseCommand):
    help = "Find overlapping ProviderSchedule blocks for manual cleanup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            type=str,
            default=None,
            help="Identity ID of a single provider to check. Omit to check all providers.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=MAX_OVERLAP_CHECK_DAYS,
            help=f"How many days ahead of today to scan (default: {MAX_OVERLAP_CHECK_DAYS}).",
        )

    def handle(self, *args, **options):
        window_start = date.today()
        window_end = window_start + timedelta(days=options["days"])

        providers_qs = HealthcareProvider.objects.select_related("identity")
        if options["provider"]:
            providers_qs = providers_qs.filter(identity__id=options["provider"])

        total_conflicts = 0
        providers_checked = 0

        for provider in providers_qs:
            schedules = list(
                ProviderSchedule.objects.filter(provider=provider).select_related("service")
            )
            if len(schedules) < 2:
                continue

            providers_checked += 1
            specs = [(s, _spec_from_schedule(s)) for s in schedules]
            provider_had_conflict = False

            for i in range(len(specs)):
                schedule_a, spec_a = specs[i]
                for j in range(i + 1, len(specs)):
                    schedule_b, spec_b = specs[j]
                    conflict_date = _find_conflicting_date(
                        spec_a, spec_b, window_start, window_end
                    )
                    if conflict_date:
                        if not provider_had_conflict:
                            name = f"{provider.identity.first_name} {provider.identity.last_name}".strip()
                            self.stdout.write(
                                self.style.WARNING(
                                    f"\nProvider {name} ({provider.identity.id}):"
                                )
                            )
                            provider_had_conflict = True

                        total_conflicts += 1
                        label_a = schedule_a.service.name if schedule_a.service else "(no service)"
                        label_b = schedule_b.service.name if schedule_b.service else "(no service)"
                        self.stdout.write(
                            f"  Conflict on {conflict_date.isoformat()}:\n"
                            f"    - schedule {schedule_a.id}  \"{label_a}\"  "
                            f"{schedule_a.start_time}-{schedule_a.end_time}  "
                            f"recurrence={schedule_a.recurrence}"
                            f"({schedule_a.recurrence_interval})\n"
                            f"    - schedule {schedule_b.id}  \"{label_b}\"  "
                            f"{schedule_b.start_time}-{schedule_b.end_time}  "
                            f"recurrence={schedule_b.recurrence}"
                            f"({schedule_b.recurrence_interval})"
                        )

        self.stdout.write("")
        if total_conflicts == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No overlaps found across {providers_checked} provider(s) "
                    f"with 2+ schedule blocks (window: {window_start} to {window_end})."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"Found {total_conflicts} conflicting pair(s) across "
                    f"{providers_checked} provider(s) checked. Review above and "
                    f"resolve manually (adjust times/dates, or delete the "
                    f"duplicate/stale block)."
                )
            )
