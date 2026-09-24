import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from powersifu.config import ConfigStore
from powersifu.engine import AutomationEngine


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ConfigStore(Path(self.temporary.name) / "config.json")
        self.store.load()
        self.store.data["automation"].update(
            {"enabled": True, "ac_profile": "balanced", "battery_profile": "power-saver"}
        )

    @patch("powersifu.engine.set_profile")
    @patch("powersifu.engine.get_active_profile", return_value="balanced")
    @patch("powersifu.engine.on_ac_power", return_value=False)
    def test_forced_battery_evaluation_selects_power_saver(self, _ac, _get, set_profile):
        engine = AutomationEngine(self.store)
        engine.tick(force_source=True)
        set_profile.assert_called_once_with("power-saver")

    @patch("powersifu.engine.set_brightness")
    def test_profile_brightness_is_applied(self, set_brightness):
        self.store.data["brightness"]["enabled"] = True
        self.store.data["brightness"]["profiles"]["power-saver"] = 35
        engine = AutomationEngine(self.store)
        engine._apply_brightness("power-saver")
        set_brightness.assert_called_once_with(35)

    @patch("powersifu.engine.set_brightness", side_effect=ValueError("bad brightness"))
    def test_brightness_failure_notifies_only_once(self, _set_brightness):
        self.store.data["brightness"]["enabled"] = True
        notifications = []
        engine = AutomationEngine(
            self.store, notify=lambda title, body: notifications.append((title, body))
        )
        engine._apply_brightness("balanced")
        engine._apply_brightness("balanced")
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0][0], "Could not change display brightness")

    @patch("powersifu.engine.stop_application", return_value=[99])
    def test_profile_rules_are_applied(self, stop_application):
        self.store.data["application_rules"] = [
            {"enabled": True, "process": "spotify", "profile": "power-saver"}
        ]
        engine = AutomationEngine(self.store)
        engine._run_application_rules("power-saver")
        stop_application.assert_called_once_with("spotify")

    def test_event_values_avoid_fallback_reads(self):
        power = Mock()
        engine = AutomationEngine(self.store, power=power)

        engine.tick(active_profile="balanced", on_ac_state=True)

        power.get_active_profile.assert_not_called()
        power.get_on_ac_power.assert_not_called()

    @patch("powersifu.engine.on_ac_power", return_value=True)
    @patch("powersifu.engine.set_profile")
    def test_schedule_runs_once_in_matching_minute(self, set_profile, _on_ac):
        self.store.data["schedules"] = [
            {
                "enabled": True,
                "label": "Morning",
                "time": "08:30",
                "days": [3],
                "profile": "balanced",
            }
        ]
        engine = AutomationEngine(self.store)
        now = datetime(2026, 9, 24, 8, 30)

        self.assertTrue(engine.run_schedules(now))
        self.assertFalse(engine.run_schedules(now))

        set_profile.assert_called_once_with("balanced")

    def test_no_schedule_work_when_list_is_empty(self):
        engine = AutomationEngine(self.store)

        self.assertFalse(engine.run_schedules(datetime(2026, 9, 24, 8, 30)))


if __name__ == "__main__":
    unittest.main()
