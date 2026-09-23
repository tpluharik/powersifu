"""Application lifecycle and system tray integration."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator3  # noqa: E402
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import __version__
from .config import APP_ID, PROFILE_NAMES, ConfigStore
from .engine import AutomationEngine
from .power import PowerProfileError, get_active_profile, on_ac_power
from .ui import PROFILE_LABELS, SettingsWindow


class PowerSifuApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.store = ConfigStore()
        self.engine: AutomationEngine | None = None
        self.window: SettingsWindow | None = None
        self.indicator: AppIndicator3.Indicator | None = None
        self.current_profile = "unknown"
        self.current_on_ac = False
        self._timeout_id = 0

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        self.hold()
        self.store.load()
        self.engine = AutomationEngine(
            self.store,
            notify=self._notify,
            state_changed=self._state_changed,
        )
        self._create_indicator()
        poll_seconds = self.store.data["automation"]["poll_seconds"]
        self._timeout_id = GLib.timeout_add_seconds(poll_seconds, self._tick)
        GLib.idle_add(self._initial_tick)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        arguments = command_line.get_arguments()[1:]
        if "--version" in arguments:
            command_line.print_literal(f"PowerSifu {__version__}\n")
            return 0
        if "--background" not in arguments:
            self.activate()
        return 0

    def do_activate(self) -> None:
        if self.window is None:
            if self.engine is None:
                return
            self.window = SettingsWindow(self, self.store, self.engine)
            self.window.connect("delete-event", self._hide_window)
        self.window.update_status(self.current_profile, self.current_on_ac)
        self.window.show_all()
        self.window.present()

    def do_shutdown(self) -> None:
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        Gtk.Application.do_shutdown(self)

    def _hide_window(self, window: Gtk.Window, _event: object) -> bool:
        window.hide()
        return True

    def _initial_tick(self) -> bool:
        if self.engine is not None:
            self.engine.tick(force_source=True)
        return GLib.SOURCE_REMOVE

    def _tick(self) -> bool:
        if self.engine is not None:
            self.engine.tick()
        return GLib.SOURCE_CONTINUE

    def _state_changed(self, profile: str, on_ac: bool) -> None:
        changed = profile != self.current_profile or on_ac != self.current_on_ac
        self.current_profile = profile
        self.current_on_ac = on_ac
        if self.window is not None:
            self.window.update_status(profile, on_ac)
        if self.indicator is not None:
            self.indicator.set_label(PROFILE_LABELS.get(profile, profile), "Current profile")
            if changed:
                self._refresh_indicator_menu()

    def _notify(self, title: str, body: str) -> None:
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new("powersifu"))
        self.send_notification("powersifu-status", notification)

    def _create_indicator(self) -> None:
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID,
            "powersifu",
            AppIndicator3.IndicatorCategory.HARDWARE,
        )
        source_icon = Path(__file__).resolve().parents[2] / "assets" / "icons" / "powersifu.png"
        if source_icon.exists():
            self.indicator.set_icon_full(str(source_icon), "PowerSifu")
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("PowerSifu")
        self._refresh_indicator_menu()

    def _refresh_indicator_menu(self) -> None:
        if self.indicator is None:
            return
        menu = Gtk.Menu()
        source = "AC" if self.current_on_ac else "Battery"
        heading = Gtk.MenuItem(label=f"{PROFILE_LABELS.get(self.current_profile, self.current_profile)} · {source}")
        heading.set_sensitive(False)
        menu.append(heading)
        menu.append(Gtk.SeparatorMenuItem())

        group: Gtk.RadioMenuItem | None = None
        for profile in PROFILE_NAMES:
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, PROFILE_LABELS[profile])
            if group is None:
                group = item
            item.set_active(profile == self.current_profile)
            item.connect("toggled", self._profile_selected, profile)
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())
        automatic = Gtk.CheckMenuItem(label="Automatic AC/battery switching")
        automatic.set_active(self.store.data["automation"]["enabled"])
        automatic.connect("toggled", self._automatic_toggled)
        menu.append(automatic)
        settings = Gtk.MenuItem(label="Settings…")
        settings.connect("activate", lambda _item: self.activate())
        menu.append(settings)
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._quit)
        menu.append(quit_item)
        menu.show_all()
        self.indicator.set_menu(menu)

    def _profile_selected(self, item: Gtk.RadioMenuItem, profile: str) -> None:
        if not item.get_active() or profile == self.current_profile or self.engine is None:
            return
        try:
            self.engine.apply_profile(profile, "Selected from tray")
        except PowerProfileError as error:
            self._notify("Could not change profile", str(error))

    def _automatic_toggled(self, item: Gtk.CheckMenuItem) -> None:
        enabled = item.get_active()
        if enabled == self.store.data["automation"]["enabled"]:
            return
        self.store.data["automation"]["enabled"] = enabled
        self.store.save()
        if enabled and self.engine is not None:
            self.engine.apply_current_source()

    def _quit(self, _item: Gtk.MenuItem) -> None:
        self.release()
        self.quit()


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"PowerSifu {__version__}")
        return 0
    application = PowerSifuApplication()
    return application.run(sys.argv)
