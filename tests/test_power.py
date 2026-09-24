import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from powersifu.power import (
    POWER_PROFILES_INTERFACE,
    UPOWER_INTERFACE,
    PowerMonitor,
    PowerProfileError,
    get_active_profile,
    on_ac_power,
    set_profile,
)


class FakeVariant:
    def __init__(self, value):
        self.value = value

    def unpack(self):
        return self.value


class FakeProxy:
    def __init__(self, properties):
        self.properties = {
            name: FakeVariant(value) for name, value in properties.items()
        }
        self.handlers = {}
        self.next_handler = 1

    def get_cached_property(self, name):
        return self.properties.get(name)

    def connect(self, _signal, callback):
        handler = self.next_handler
        self.next_handler += 1
        self.handlers[handler] = callback
        return handler

    def disconnect(self, handler):
        del self.handlers[handler]

    def change(self, name, value):
        self.properties[name] = FakeVariant(value)
        for callback in list(self.handlers.values()):
            callback(self, FakeVariant({name: value}), [])


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


class PowerMonitorTests(unittest.TestCase):
    def setUp(self):
        self.profile_proxy = FakeProxy({"ActiveProfile": "balanced"})
        self.source_proxy = FakeProxy({"OnBattery": False})
        self.created = []

        def factory(_name, _path, interface):
            self.created.append(interface)
            if interface == POWER_PROFILES_INTERFACE:
                return self.profile_proxy
            if interface == UPOWER_INTERFACE:
                return self.source_proxy
            raise AssertionError(f"unexpected interface {interface}")

        self.monitor = PowerMonitor(proxy_factory=factory)

    def test_reuses_one_proxy_per_service(self):
        self.assertEqual(self.monitor.get_active_profile(), "balanced")
        self.assertEqual(self.monitor.get_active_profile(), "balanced")
        self.assertTrue(self.monitor.get_on_ac_power())
        self.assertTrue(self.monitor.get_on_ac_power())

        self.assertEqual(
            self.created,
            [POWER_PROFILES_INTERFACE, UPOWER_INTERFACE],
        )

    def test_emits_only_actual_property_changes(self):
        profiles = []
        sources = []
        self.assertEqual(self.monitor.start(profiles.append, sources.append), [])

        self.profile_proxy.change("ActiveProfile", "balanced")
        self.profile_proxy.change("ActiveProfile", "power-saver")
        self.source_proxy.change("OnBattery", False)
        self.source_proxy.change("OnBattery", True)

        self.assertEqual(profiles, ["power-saver"])
        self.assertEqual(sources, [False])

    def test_close_disconnects_signal_handlers(self):
        self.monitor.start(lambda _profile: None, lambda _source: None)

        self.monitor.close()

        self.assertEqual(self.profile_proxy.handlers, {})
        self.assertEqual(self.source_proxy.handlers, {})


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
