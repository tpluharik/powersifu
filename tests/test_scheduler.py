import unittest
from datetime import datetime

from powersifu.scheduler import format_days, schedule_key, schedule_matches


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


if __name__ == "__main__":
    unittest.main()
