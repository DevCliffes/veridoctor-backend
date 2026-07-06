"""
Management command: repair_schedule_end_dates

One-off data-repair for ProviderSchedule rows created before the
recurrence_end_type-aware end_date fix. Previously, only
recurrence_end_type == "never" got its end_date correctly overridden to
the 2099-12-31 sentinel; "on_date" and "after" schedules were persisted
with whatever end_date the client happened to submit (which, due to a
separate frontend bug, was often an unrelated stray date). This command
recomputes the *correct* end_date for every existing recurring schedule
using the same _resolve_end_date logic the views now use going forward,
and updates any row whose stored end_date doesn't match.

USAGE:
    # Preview changes without writing anything (default):
    python manage.py repair_schedule_end_dates

    # Actually apply the fix:
    python manage.py repair_schedule_end_dates --apply

Place this file at:
    <your_app>/management/commands/repair_schedule_end_dates.py
(create the management/ and management/commands/ directories, each with
an __init__.py, if they don't already exist in your provider app).
"""

from django.core.management.base import BaseCommand
from provider.models import ProviderSchedule
from provider.views import _resolve_end_date


class Command(BaseCommand):
    help = (
        "Recomputes end_date for existing recurring ProviderSchedule rows "
        "based on recurrence_end_type, fixing rows created before the "
        "on_date/after handling was added. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write the corrected end_date values. Without "
                 "this flag, the command only prints what it would change.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        schedules = ProviderSchedule.objects.exclude(recurrence="none")
        total = schedules.count()
        changed = 0
        skipped_no_data = 0

        self.stdout.write(f"Scanning {total} recurring schedule row(s)...\n")

        for s in schedules:
            resolved = _resolve_end_date(
                recurrence=s.recurrence,
                end_type=s.recurrence_end_type,
                start_date=s.start_date,
                recurrence_days=s.recurrence_days or [],
                recurrence_interval=s.recurrence_interval or 1,
                recurrence_end_date=(
                    s.recurrence_end_date.isoformat() if s.recurrence_end_date else None
                ),
                recurrence_count=s.recurrence_count,
            )

            if not resolved:
                # e.g. "after" type with no recurrence_count set, or
                # "on_date" with no recurrence_end_date -- nothing to fix
                # from the data we have; flag it for manual review.
                skipped_no_data += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  SKIP  {s.id}  ({s.service.name if s.service else 'no service'}, "
                        f"{s.recurrence}/{s.recurrence_end_type}) -- insufficient data to "
                        f"compute end_date, left untouched."
                    )
                )
                continue

            current_end = s.end_date.isoformat()
            if resolved == current_end:
                continue  # already correct

            changed += 1
            label = s.service.name if s.service else "no service"
            self.stdout.write(
                f"  {'APPLY' if apply_changes else 'WOULD APPLY'}  {s.id}  ({label}, "
                f"{s.recurrence}/{s.recurrence_end_type}): "
                f"end_date {current_end} -> {resolved}"
            )

            if apply_changes:
                s.end_date = resolved
                s.save(update_fields=["end_date"])

        self.stdout.write("")
        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. {changed} row(s) updated, {skipped_no_data} skipped "
                    f"(insufficient data), {total - changed - skipped_no_data} already correct."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run complete. {changed} row(s) WOULD be updated, "
                    f"{skipped_no_data} skipped (insufficient data), "
                    f"{total - changed - skipped_no_data} already correct."
                )
            )
            self.stdout.write("Re-run with --apply to write these changes.")
