import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from powersifu.processes import (
    DESKTOP_PROTECTED_NAMES,
    matching_processes,
    stop_application,
    validate_process_name,
)


class ProcessTests(unittest.TestCase):
    def test_validates_exact_names_and_protects_desktop(self):
        self.assertTrue(validate_process_name("spotify"))
        self.assertTrue(validate_process_name("signal-desktop"))
        self.assertFalse(validate_process_name("spotify; reboot"))
        self.assertFalse(validate_process_name("gnome-shell"))
        self.assertFalse(validate_process_name("xorg"))

    def test_protects_every_advertised_desktop(self):
        self.assertEqual(
            set(DESKTOP_PROTECTED_NAMES),
            {"GNOME", "KDE", "Unity", "XFCE", "LXQt", "MATE", "Cinnamon"},
        )
        for desktop, names in DESKTOP_PROTECTED_NAMES.items():
            with self.subTest(desktop=desktop):
                self.assertTrue(names)
                for name in names:
                    self.assertFalse(validate_process_name(name), name)

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

    def test_session_leader_is_never_matched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = root / "1234"
            process.mkdir()
            (process / "comm").write_text("spotify\n")
            (process / "stat").write_text(
                "1234 (spotify) S 1 1234 1234 0 -1 0 0 0 0 0 0 0 0 0 0 0 0 0\n"
            )
            self.assertEqual(matching_processes("spotify", root), [])

    @patch("powersifu.processes.os.kill")
    @patch("powersifu.processes.os.pidfd_open", create=True, side_effect=OSError)
    def test_rechecks_identity_before_signalling(self, _pidfd_open, kill):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = root / "1234"
            process.mkdir()
            (process / "comm").write_text("spotify\n")

            original_matching = matching_processes

            def replace_after_match(name, proc_root):
                matches = original_matching(name, proc_root)
                (process / "comm").write_text("different-process\n")
                return matches

            with patch("powersifu.processes.matching_processes", side_effect=replace_after_match):
                self.assertEqual(stop_application("spotify", root), [])
            kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
