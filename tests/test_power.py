import tempfile
import unittest
from pathlib import Path

from powersifu.power import on_ac_power


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
