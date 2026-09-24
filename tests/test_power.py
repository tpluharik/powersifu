import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from powersifu.power import PowerProfileError, get_active_profile, on_ac_power, set_profile


class PowerProfileTests(unittest.TestCase):
    def test_reads_supported_profile(self):
        reader = Mock(return_value="balanced")

        self.assertEqual(get_active_profile(reader), "balanced")
        reader.assert_called_once_with()

    def test_rejects_unknown_active_profile(self):
        with self.assertRaisesRegex(PowerProfileError, "Unknown active profile"):
            get_active_profile(lambda: "turbo")

    def test_writes_supported_profile(self):
        writer = Mock()

        set_profile("power-saver", writer)

        writer.assert_called_once_with("power-saver")

    def test_rejects_unsupported_target_profile(self):
        writer = Mock()

        with self.assertRaisesRegex(ValueError, "Unsupported power profile"):
            set_profile("turbo", writer)

        writer.assert_not_called()


class PowerSupplyTests(unittest.TestCase):
    def _supply(self, root: Path, name: str, kind: str, online: str) -> None:
        supply = root / name
        supply.mkdir()
        (supply / "type").write_text(kind)
        (supply / "online").write_text(online)

    def test_detects_online_mains(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._supply(root, "AC", "Mains", "1")
            self.assertTrue(on_ac_power(root))

    def test_ignores_offline_supply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._supply(root, "AC", "Mains", "0")
            self.assertFalse(on_ac_power(root))


if __name__ == "__main__":
    unittest.main()
