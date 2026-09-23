import tempfile
import unittest
from pathlib import Path

from powersifu.processes import matching_processes, validate_process_name


class ProcessTests(unittest.TestCase):
    def test_validates_exact_names_and_protects_desktop(self):
        self.assertTrue(validate_process_name("spotify"))
        self.assertTrue(validate_process_name("signal-desktop"))
        self.assertFalse(validate_process_name("spotify; reboot"))
        self.assertFalse(validate_process_name("gnome-shell"))
        self.assertFalse(validate_process_name("xorg"))

    def test_exact_process_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = root / "1234"
            process.mkdir()
            (process / "comm").write_text("spotify\n")
            other = root / "5678"
            other.mkdir()
            (other / "comm").write_text("spotify-helper\n")
            self.assertEqual(matching_processes("spotify", root), [1234])


if __name__ == "__main__":
    unittest.main()
