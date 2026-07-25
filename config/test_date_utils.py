from datetime import datetime, timezone

from django.test import SimpleTestCase

from config.date_utils import add_service_duration


class AddServiceDurationTests(SimpleTestCase):
    def test_one_month_preserves_calendar_day(self):
        start = datetime(2026, 7, 12, 15, 30, tzinfo=timezone.utc)
        self.assertEqual(
            add_service_duration(start, 30),
            datetime(2026, 8, 12, 15, 30, tzinfo=timezone.utc),
        )

    def test_three_months_preserve_calendar_day(self):
        start = datetime(2026, 7, 12, 15, 30, tzinfo=timezone.utc)
        self.assertEqual(
            add_service_duration(start, 90),
            datetime(2026, 10, 12, 15, 30, tzinfo=timezone.utc),
        )

    def test_end_of_month_clamps_safely(self):
        start = datetime(2025, 1, 31, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(
            add_service_duration(start, 30),
            datetime(2025, 2, 28, 10, 0, tzinfo=timezone.utc),
        )

    def test_non_month_duration_uses_exact_days(self):
        start = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(
            add_service_duration(start, 15),
            datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
        )
