import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
