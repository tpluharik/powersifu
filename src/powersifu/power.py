"""Event-driven interfaces to power-profiles-daemon and UPower."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import PROFILE_NAMES


POWER_PROFILES_NAME = "org.freedesktop.UPower.PowerProfiles"
POWER_PROFILES_PATH = "/org/freedesktop/UPower/PowerProfiles"
POWER_PROFILES_INTERFACE = "org.freedesktop.UPower.PowerProfiles"
UPOWER_NAME = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"
UPOWER_INTERFACE = "org.freedesktop.UPower"
DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
DBUS_TIMEOUT_MS = 3_000

ProxyFactory = Callable[[str, str, str], Any]
ProfileCallback = Callable[[str], None]
SourceCallback = Callable[[bool], None]


class PowerProfileError(RuntimeError):
    pass


def _dbus_modules():
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as error:
        raise PowerProfileError("The Gio D-Bus integration is not installed") from error
    return Gio, GLib


def _new_system_proxy(name: str, path: str, interface: str):
    Gio, GLib = _dbus_modules()
    try:
        return Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            name,
            path,
            interface,
            None,
        )
    except GLib.Error as error:
        raise PowerProfileError(f"Could not connect to the power service: {error.message}") from error


def _validated_profile(value: object) -> str:
    profile = str(value)
    if profile not in PROFILE_NAMES:
        raise PowerProfileError(f"Unknown active profile: {profile}")
    return profile


class PowerMonitor:
    """Keep shared D-Bus proxies and emit changes from their property signals."""

    def __init__(self, proxy_factory: ProxyFactory = _new_system_proxy) -> None:
        self._proxy_factory = proxy_factory
        self._profile_proxy: Any | None = None
        self._source_proxy: Any | None = None
        self._profile_handler = 0
        self._source_handler = 0
        self._profile_callback: ProfileCallback | None = None
        self._source_callback: SourceCallback | None = None
        self._last_profile: str | None = None
        self._last_on_ac: bool | None = None

    def _profiles(self):
        if self._profile_proxy is None:
            self._profile_proxy = self._proxy_factory(
                POWER_PROFILES_NAME,
                POWER_PROFILES_PATH,
                POWER_PROFILES_INTERFACE,
            )
        return self._profile_proxy

    def _upower(self):
        if self._source_proxy is None:
            self._source_proxy = self._proxy_factory(
                UPOWER_NAME,
                UPOWER_PATH,
                UPOWER_INTERFACE,
            )
        return self._source_proxy

    def _remote_property(self, proxy: Any, interface: str, name: str) -> object:
        Gio, GLib = _dbus_modules()
        try:
            response = proxy.get_connection().call_sync(
                proxy.get_name(),
                proxy.get_object_path(),
                DBUS_PROPERTIES_INTERFACE,
                "Get",
                GLib.Variant("(ss)", (interface, name)),
                GLib.VariantType.new("(v)"),
                Gio.DBusCallFlags.NONE,
                DBUS_TIMEOUT_MS,
                None,
            )
        except GLib.Error as error:
            raise PowerProfileError(f"Could not read {name}: {error.message}") from error
        return response.unpack()[0]

    def get_active_profile(self, *, refresh: bool = False) -> str:
        proxy = self._profiles()
        value = None if refresh else proxy.get_cached_property("ActiveProfile")
        if value is None:
            return _validated_profile(
                self._remote_property(proxy, POWER_PROFILES_INTERFACE, "ActiveProfile")
            )
        return _validated_profile(value.unpack())

    def get_on_ac_power(self, *, refresh: bool = False) -> bool:
        try:
            proxy = self._upower()
            value = None if refresh else proxy.get_cached_property("OnBattery")
            if value is None:
                value = self._remote_property(proxy, UPOWER_INTERFACE, "OnBattery")
            else:
                value = value.unpack()
            return not bool(value)
        except PowerProfileError:
            return on_ac_power()

    def set_profile(self, profile: str) -> None:
        if profile not in PROFILE_NAMES:
            raise ValueError(f"Unsupported power profile: {profile}")
        Gio, GLib = _dbus_modules()
        proxy = self._profiles()
        try:
            proxy.get_connection().call_sync(
                POWER_PROFILES_NAME,
                POWER_PROFILES_PATH,
                DBUS_PROPERTIES_INTERFACE,
                "Set",
                GLib.Variant(
                    "(ssv)",
                    (
                        POWER_PROFILES_INTERFACE,
                        "ActiveProfile",
                        GLib.Variant("s", profile),
                    ),
                ),
                None,
                Gio.DBusCallFlags.NONE,
                DBUS_TIMEOUT_MS,
                None,
            )
        except GLib.Error as error:
            message = f"Could not change the power profile: {error.message}"
            raise PowerProfileError(message) from error
        self._last_profile = profile

    def start(
        self,
        profile_changed: ProfileCallback,
        source_changed: SourceCallback,
    ) -> list[str]:
        """Subscribe to service changes and return any unavailable signal sources."""

        self.close()
        self._profile_callback = profile_changed
        self._source_callback = source_changed
        warnings: list[str] = []
        try:
            profile_proxy = self._profiles()
            self._last_profile = self.get_active_profile()
            self._profile_handler = profile_proxy.connect(
                "g-properties-changed",
                self._profile_properties_changed,
            )
        except PowerProfileError as error:
            warnings.append(str(error))
        try:
            source_proxy = self._upower()
            self._last_on_ac = self.get_on_ac_power()
            self._source_handler = source_proxy.connect(
                "g-properties-changed",
                self._source_properties_changed,
            )
        except PowerProfileError as error:
            warnings.append(str(error))
        return warnings

    def close(self) -> None:
        if self._profile_proxy is not None and self._profile_handler:
            self._profile_proxy.disconnect(self._profile_handler)
        if self._source_proxy is not None and self._source_handler:
            self._source_proxy.disconnect(self._source_handler)
        self._profile_handler = 0
        self._source_handler = 0
        self._profile_callback = None
        self._source_callback = None

    def _profile_properties_changed(self, *_arguments: object) -> None:
        try:
            profile = self.get_active_profile()
        except PowerProfileError:
            return
        if profile == self._last_profile:
            return
        self._last_profile = profile
        if self._profile_callback is not None:
            self._profile_callback(profile)

    def _source_properties_changed(self, *_arguments: object) -> None:
        on_ac = self.get_on_ac_power()
        if on_ac == self._last_on_ac:
            return
        self._last_on_ac = on_ac
        if self._source_callback is not None:
            self._source_callback(on_ac)


_DEFAULT_MONITOR = PowerMonitor()


def get_active_profile(reader: Callable[[], str] | None = None) -> str:
    """Read the daemon's active profile through a persistent D-Bus proxy."""

    profile = (reader or _DEFAULT_MONITOR.get_active_profile)()
    return _validated_profile(profile)


def set_profile(profile: str, writer: Callable[[str], None] | None = None) -> None:
    """Set a supported profile directly through the daemon's system D-Bus API."""

    if profile not in PROFILE_NAMES:
        raise ValueError(f"Unsupported power profile: {profile}")
    (writer or _DEFAULT_MONITOR.set_profile)(profile)


def on_ac_power(root: Path = Path("/sys/class/power_supply")) -> bool:
    """Return True when an online mains-class supply is present."""

    if not root.exists():
        return False
    for supply in root.iterdir():
        try:
            supply_type = (supply / "type").read_text(encoding="utf-8").strip()
            online = (supply / "online").read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if supply_type in {"Mains", "USB", "USB_C", "USB_PD"} and online == "1":
            return True
    return False
