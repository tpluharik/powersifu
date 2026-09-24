import unittest
from datetime import datetime

from powersifu.scheduler import (
    format_days,
    milliseconds_until_next_minute,
    schedule_key,
    schedule_matches,
)


class SchedulerTests(unittest.TestCase):
    def test_weekday_schedule(self):
        monday = datetime(2026, 9, 21, 8, 30)
        schedule = {"enabled": True, "time": "08:30", "days": list(range(5))}
        self.assertTrue(schedule_matches(schedule, monday))
        self.assertEqual(format_days(schedule["days"]), "Weekdays")
        self.assertEqual(schedule_key(2, monday), "2026-09-21T08:30:2")

    def test_disabled_schedule_does_not_match(self):
        monday = datetime(2026, 9, 21, 8, 30)
        self.assertFalse(
            schedule_matches({"enabled": False, "time": "08:30", "days": [0]}, monday)
        )

    def test_next_check_aligns_to_wall_clock_minute(self):
        now = datetime(2026, 9, 24, 8, 30, 42, 250_000)

        self.assertEqual(milliseconds_until_next_minute(now), 17_750)


if __name__ == "__main__":
    unittest.main()
