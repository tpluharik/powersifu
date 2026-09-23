"""GTK 3 settings window for PowerSifu."""

from __future__ import annotations

import threading
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, GObject, Gtk  # noqa: E402

from . import __version__
from .brightness import BrightnessError, set_brightness
from .config import PROFILE_NAMES, ConfigStore, sync_autostart
from .engine import AutomationEngine
from .processes import validate_process_name
from .scheduler import DAY_NAMES, format_days
from .updates import (
    UpdateCheckError,
    UpdateInfo,
    UpdateInstallError,
    check_for_update,
    download_update,
    install_update,
)


PROFILE_LABELS = {
    "power-saver": "Power Saver",
    "balanced": "Balanced",
    "performance": "Performance",
}


def profile_combo(selected: str = "balanced") -> Gtk.ComboBoxText:
    combo = Gtk.ComboBoxText()
    for profile in PROFILE_NAMES:
        combo.append(profile, PROFILE_LABELS[profile])
    combo.set_active_id(selected)
    return combo


def _label(text: str, *, markup: bool = False) -> Gtk.Label:
    label = Gtk.Label()
    if markup:
        label.set_markup(text)
    else:
        label.set_text(text)
    label.set_xalign(0)
    label.set_line_wrap(True)
    return label


class RuleDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, rule: dict[str, Any] | None = None) -> None:
        super().__init__(
            title="Application rule",
            transient_for=parent,
            modal=True,
            use_header_bar=True,
        )
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(420, -1)
        rule = rule or {"enabled": True, "process": "", "profile": "power-saver"}

        grid = Gtk.Grid(column_spacing=12, row_spacing=12, margin=18)
        grid.attach(_label("<b>Exact process name</b>", markup=True), 0, 0, 1, 1)
        self.process_entry = Gtk.Entry(text=rule["process"])
        self.process_entry.set_placeholder_text("spotify")
        self.process_entry.set_activates_default(True)
        grid.attach(self.process_entry, 1, 0, 1, 1)
        grid.attach(_label("<b>When profile becomes</b>", markup=True), 0, 1, 1, 1)
        self.profile = profile_combo(rule["profile"])
        grid.attach(self.profile, 1, 1, 1, 1)
        self.enabled = Gtk.CheckButton(label="Rule enabled")
        self.enabled.set_active(rule["enabled"])
        grid.attach(self.enabled, 0, 2, 2, 1)
        hint = _label(
            "PowerSifu sends SIGTERM only to exact matches owned by your user. "
            "Core desktop processes are protected."
        )
        hint.get_style_context().add_class("dim-label")
        grid.attach(hint, 0, 3, 2, 1)
        self.get_content_area().add(grid)
        self.show_all()

    def value(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.get_active(),
            "process": self.process_entry.get_text().strip(),
            "profile": self.profile.get_active_id(),
        }


class ScheduleDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, schedule: dict[str, Any] | None = None) -> None:
        super().__init__(
            title="Profile schedule",
            transient_for=parent,
            modal=True,
            use_header_bar=True,
        )
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(500, -1)
        schedule = schedule or {
            "enabled": True,
            "label": "",
            "time": "22:00",
            "days": list(range(7)),
            "profile": "power-saver",
        }

        grid = Gtk.Grid(column_spacing=12, row_spacing=12, margin=18)
        grid.attach(_label("<b>Label</b>", markup=True), 0, 0, 1, 1)
        self.label_entry = Gtk.Entry(text=schedule.get("label", ""))
        self.label_entry.set_placeholder_text("Evening battery saver")
        grid.attach(self.label_entry, 1, 0, 1, 1)

        grid.attach(_label("<b>Time</b>", markup=True), 0, 1, 1, 1)
        time_box = Gtk.Box(spacing=6)
        hour, minute = (int(part) for part in schedule["time"].split(":"))
        self.hour = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.minute = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.hour.set_value(hour)
        self.minute.set_value(minute)
        time_box.pack_start(self.hour, False, False, 0)
        time_box.pack_start(Gtk.Label(label=":"), False, False, 0)
        time_box.pack_start(self.minute, False, False, 0)
        grid.attach(time_box, 1, 1, 1, 1)

        grid.attach(_label("<b>Days</b>", markup=True), 0, 2, 1, 1)
        days_box = Gtk.Box(spacing=4)
        self.day_buttons: list[Gtk.ToggleButton] = []
        for index, day in enumerate(DAY_NAMES):
            button = Gtk.ToggleButton(label=day)
            button.set_active(index in schedule["days"])
            self.day_buttons.append(button)
            days_box.pack_start(button, True, True, 0)
        grid.attach(days_box, 1, 2, 1, 1)

        grid.attach(_label("<b>Switch to</b>", markup=True), 0, 3, 1, 1)
        self.profile = profile_combo(schedule["profile"])
        grid.attach(self.profile, 1, 3, 1, 1)
        self.enabled = Gtk.CheckButton(label="Schedule enabled")
        self.enabled.set_active(schedule["enabled"])
        grid.attach(self.enabled, 0, 4, 2, 1)
        self.get_content_area().add(grid)
        self.show_all()

    def value(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.get_active(),
            "label": self.label_entry.get_text().strip(),
            "time": f"{self.hour.get_value_as_int():02d}:{self.minute.get_value_as_int():02d}",
            "days": [index for index, button in enumerate(self.day_buttons) if button.get_active()],
            "profile": self.profile.get_active_id(),
        }


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application, store: ConfigStore, engine: AutomationEngine) -> None:
        super().__init__(application=application, title="PowerSifu")
        self.store = store
        self.engine = engine
        self._active_profile = "unknown"
        self._available_update: UpdateInfo | None = None
        self._update_uri: str | None = None
        self.set_default_size(800, 600)
        self.set_icon_name("powersifu")

        header = Gtk.HeaderBar(title="PowerSifu", subtitle="Power profiles under control")
        header.set_show_close_button(True)
        save_button = Gtk.Button.new_with_label("Save")
        save_button.get_style_context().add_class("suggested-action")
        save_button.connect("clicked", self._save)
        header.pack_end(save_button)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)
        self.notebook = Gtk.Notebook()
        self.notebook.set_border_width(12)
        root.pack_start(self.notebook, True, True, 0)

        self._build_general_page()
        self._build_brightness_page()
        self._build_rules_page()
        self._build_schedules_page()
        self._build_about_page()
        self._load_from_config()

    def _build_general_page(self) -> None:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=14)

        state_frame = Gtk.Frame(label=" Current state ")
        state_grid = Gtk.Grid(column_spacing=18, row_spacing=8, margin=14)
        self.profile_state = _label("Unknown")
        self.source_state = _label("Unknown")
        state_grid.attach(_label("<b>Profile</b>", markup=True), 0, 0, 1, 1)
        state_grid.attach(self.profile_state, 1, 0, 1, 1)
        state_grid.attach(_label("<b>Power source</b>", markup=True), 0, 1, 1, 1)
        state_grid.attach(self.source_state, 1, 1, 1, 1)
        state_frame.add(state_grid)
        page.pack_start(state_frame, False, False, 0)

        automation_frame = Gtk.Frame(label=" Automatic source switching ")
        grid = Gtk.Grid(column_spacing=18, row_spacing=12, margin=14)
        self.auto_enabled = Gtk.CheckButton(label="Change profile when AC power changes")
        grid.attach(self.auto_enabled, 0, 0, 2, 1)
        grid.attach(_label("When plugged in"), 0, 1, 1, 1)
        self.ac_profile = profile_combo()
        grid.attach(self.ac_profile, 1, 1, 1, 1)
        grid.attach(_label("When running on battery"), 0, 2, 1, 1)
        self.battery_profile = profile_combo("power-saver")
        grid.attach(self.battery_profile, 1, 2, 1, 1)
        apply_button = Gtk.Button.new_with_label("Apply current source rule now")
        apply_button.connect("clicked", self._apply_source)
        grid.attach(apply_button, 0, 3, 2, 1)
        automation_frame.add(grid)
        page.pack_start(automation_frame, False, False, 0)

        startup_frame = Gtk.Frame(label=" Startup ")
        startup_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=14)
        self.start_at_login = Gtk.CheckButton(label="Start PowerSifu in the tray when I sign in")
        startup_box.pack_start(self.start_at_login, False, False, 0)
        startup_frame.add(startup_box)
        page.pack_start(startup_frame, False, False, 0)
        self.notebook.append_page(page, Gtk.Label(label="General"))

    def _build_brightness_page(self) -> None:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=14)
        page.pack_start(
            _label(
                "Optionally set the built-in display brightness whenever a power profile "
                "becomes active. Saving settings applies the current profile immediately."
            ),
            False,
            False,
            0,
        )
        self.brightness_profile_status = _label(
            "Current profile: Unknown. Use Apply now to preview any configured value."
        )
        self.brightness_profile_status.get_style_context().add_class("dim-label")
        page.pack_start(self.brightness_profile_status, False, False, 0)

        frame = Gtk.Frame(label=" Profile brightness ")
        grid = Gtk.Grid(column_spacing=18, row_spacing=12, margin=14)
        self.brightness_enabled = Gtk.CheckButton(
            label="Change display brightness with the power profile"
        )
        self.brightness_enabled.connect("toggled", self._brightness_enabled_toggled)
        grid.attach(self.brightness_enabled, 0, 0, 3, 1)

        self.brightness_values: dict[str, Gtk.SpinButton] = {}
        self.brightness_labels: dict[str, Gtk.Label] = {}
        self.brightness_apply_buttons: dict[str, Gtk.Button] = {}
        for row, profile in enumerate(PROFILE_NAMES, start=1):
            profile_label = _label(PROFILE_LABELS[profile])
            grid.attach(profile_label, 0, row, 1, 1)
            value = Gtk.SpinButton.new_with_range(1, 100, 1)
            value.set_numeric(True)
            value.set_tooltip_text("Brightness percentage for this power profile")
            grid.attach(value, 1, row, 1, 1)
            grid.attach(Gtk.Label(label="%"), 2, row, 1, 1)
            apply_button = Gtk.Button.new_with_label("Apply now")
            apply_button.set_tooltip_text(
                "Preview this brightness immediately without changing the active power profile"
            )
            apply_button.connect("clicked", self._apply_brightness_preview, profile)
            grid.attach(apply_button, 3, row, 1, 1)
            self.brightness_values[profile] = value
            self.brightness_labels[profile] = profile_label
            self.brightness_apply_buttons[profile] = apply_button

        hint = _label(
            "PowerSifu uses the desktop session or brightnessctl and never asks for root access. "
            "External monitors may require their own display controls."
        )
        hint.get_style_context().add_class("dim-label")
        grid.attach(hint, 0, 4, 4, 1)
        frame.add(grid)
        page.pack_start(frame, False, False, 0)
        self.notebook.append_page(page, Gtk.Label(label="Brightness"))

    def _build_rules_page(self) -> None:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        page.pack_start(
            _label(
                "Stop selected applications when a profile becomes active. Rules use an exact "
                "Linux process name and send a graceful termination request."
            ),
            False,
            False,
            0,
        )
        self.rules_model = Gtk.ListStore(bool, str, str)
        self.rules_view = Gtk.TreeView(model=self.rules_model)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._toggle_rule)
        self.rules_view.append_column(Gtk.TreeViewColumn("Enabled", toggle, active=0))
        self.rules_view.append_column(Gtk.TreeViewColumn("Process", Gtk.CellRendererText(), text=1))
        self.rules_view.append_column(Gtk.TreeViewColumn("When profile becomes", Gtk.CellRendererText(), text=2))
        self.rules_view.connect("row-activated", lambda *_args: self._edit_rule())
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.rules_view)
        page.pack_start(scroll, True, True, 0)
        buttons = Gtk.Box(spacing=6)
        for text, callback in (("Add", self._add_rule), ("Edit", self._edit_rule), ("Remove", self._remove_rule)):
            button = Gtk.Button.new_with_label(text)
            button.connect("clicked", lambda _button, fn=callback: fn())
            buttons.pack_start(button, False, False, 0)
        page.pack_start(buttons, False, False, 0)
        self.notebook.append_page(page, Gtk.Label(label="Application Rules"))

    def _build_schedules_page(self) -> None:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        page.pack_start(
            _label("Create recurring weekly times that switch the system power profile."),
            False,
            False,
            0,
        )
        self.schedules_model = Gtk.ListStore(bool, str, str, str, str, GObject.TYPE_PYOBJECT)
        self.schedules_view = Gtk.TreeView(model=self.schedules_model)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._toggle_schedule)
        columns = (
            ("Enabled", toggle, "active", 0),
            ("Label", Gtk.CellRendererText(), "text", 1),
            ("Time", Gtk.CellRendererText(), "text", 2),
            ("Days", Gtk.CellRendererText(), "text", 3),
            ("Profile", Gtk.CellRendererText(), "text", 4),
        )
        for title, renderer, attribute, index in columns:
            self.schedules_view.append_column(Gtk.TreeViewColumn(title, renderer, **{attribute: index}))
        self.schedules_view.connect("row-activated", lambda *_args: self._edit_schedule())
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.schedules_view)
        page.pack_start(scroll, True, True, 0)
        buttons = Gtk.Box(spacing=6)
        for text, callback in (
            ("Add", self._add_schedule),
            ("Edit", self._edit_schedule),
            ("Remove", self._remove_schedule),
        ):
            button = Gtk.Button.new_with_label(text)
            button.connect("clicked", lambda _button, fn=callback: fn())
            buttons.pack_start(button, False, False, 0)
        page.pack_start(buttons, False, False, 0)
        self.notebook.append_page(page, Gtk.Label(label="Schedules"))

    def _build_about_page(self) -> None:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=28)
        image = Gtk.Image.new_from_icon_name("powersifu", Gtk.IconSize.DIALOG)
        page.pack_start(image, False, False, 4)
        title = _label("<span size='xx-large' weight='bold'>PowerSifu</span>", markup=True)
        title.set_xalign(0.5)
        page.pack_start(title, False, False, 0)
        description = _label(
            "A small Linux tray utility for automatic power-profile switching, "
            "profile-aware brightness, weekly schedules, and application rules."
        )
        description.set_justify(Gtk.Justification.CENTER)
        description.set_xalign(0.5)
        page.pack_start(description, False, False, 0)
        version = _label(f"Version {__version__}")
        version.set_xalign(0.5)
        page.pack_start(version, False, False, 0)
        safety = _label(
            "PowerSifu never executes user-provided shell commands. Application rules only "
            "match exact same-user process names, and critical desktop processes are protected."
        )
        safety.set_justify(Gtk.Justification.CENTER)
        safety.set_xalign(0.5)
        page.pack_start(safety, False, False, 12)

        self.update_check_status = _label("Updates are checked only when you request it.")
        self.update_check_status.set_justify(Gtk.Justification.CENTER)
        self.update_check_status.set_xalign(0.5)
        page.pack_start(self.update_check_status, False, False, 0)
        update_buttons = Gtk.Box(spacing=8)
        update_buttons.set_halign(Gtk.Align.CENTER)
        self.update_check_button = Gtk.Button.new_with_label("Check for updates")
        self.update_check_button.connect("clicked", self._check_for_updates)
        update_buttons.pack_start(self.update_check_button, False, False, 0)
        self.update_action_button = Gtk.Button.new_with_label("Install update")
        self.update_action_button.connect("clicked", self._update_action)
        self.update_action_button.set_no_show_all(True)
        self.update_action_button.hide()
        update_buttons.pack_start(self.update_action_button, False, False, 0)
        page.pack_start(update_buttons, False, False, 0)
        self.notebook.append_page(page, Gtk.Label(label="About"))

    def _load_from_config(self) -> None:
        config = self.store.data
        automation = config["automation"]
        self.auto_enabled.set_active(automation["enabled"])
        self.ac_profile.set_active_id(automation["ac_profile"])
        self.battery_profile.set_active_id(automation["battery_profile"])
        self.start_at_login.set_active(config["start_at_login"])
        brightness = config["brightness"]
        self.brightness_enabled.set_active(brightness["enabled"])
        for profile, value in self.brightness_values.items():
            value.set_value(brightness["profiles"][profile])
        self._brightness_enabled_toggled(self.brightness_enabled)

        self.rules_model.clear()
        for rule in config["application_rules"]:
            self.rules_model.append(
                [rule["enabled"], rule["process"], rule["profile"]]
            )
        self.schedules_model.clear()
        for schedule in config["schedules"]:
            self.schedules_model.append(
                [
                    schedule["enabled"],
                    schedule["label"],
                    schedule["time"],
                    format_days(schedule["days"]),
                    schedule["profile"],
                    schedule["days"],
                ]
            )

    def update_status(self, profile: str, on_ac: bool) -> None:
        self._active_profile = profile
        self.profile_state.set_text(PROFILE_LABELS.get(profile, profile))
        self.source_state.set_text("AC power" if on_ac else "Battery")
        for name, label in self.brightness_labels.items():
            suffix = " (active)" if name == profile else ""
            label.set_text(f"{PROFILE_LABELS[name]}{suffix}")
        if profile in self.brightness_values:
            percent = self.brightness_values[profile].get_value_as_int()
            self.brightness_profile_status.set_text(
                f"Current profile: {PROFILE_LABELS[profile]} — configured brightness {percent}%."
            )
        else:
            self.brightness_profile_status.set_text("Current profile: Unknown")

    def _save(self, _button: Gtk.Button) -> None:
        config = self.store.data
        config["start_at_login"] = self.start_at_login.get_active()
        config["automation"].update(
            {
                "enabled": self.auto_enabled.get_active(),
                "ac_profile": self.ac_profile.get_active_id(),
                "battery_profile": self.battery_profile.get_active_id(),
            }
        )
        config["brightness"] = {
            "enabled": self.brightness_enabled.get_active(),
            "profiles": {
                profile: value.get_value_as_int()
                for profile, value in self.brightness_values.items()
            },
        }
        config["application_rules"] = [
            {"enabled": row[0], "process": row[1], "profile": row[2]}
            for row in self.rules_model
        ]
        config["schedules"] = [
            {
                "enabled": row[0],
                "label": row[1],
                "time": row[2],
                "days": list(row[5]),
                "profile": row[4],
            }
            for row in self.schedules_model
        ]
        try:
            self.store.save()
            sync_autostart(config["start_at_login"])
            self.engine.apply_current_source()
        except (OSError, ValueError) as error:
            self._message("Could not save settings", str(error), Gtk.MessageType.ERROR)
            return
        if self.engine.last_brightness_error:
            self._message(
                "Settings saved, but brightness was not changed",
                self.engine.last_brightness_error,
                Gtk.MessageType.WARNING,
            )
            return
        self._message("Settings saved", "PowerSifu is using the updated rules.", Gtk.MessageType.INFO)

    def _brightness_enabled_toggled(self, button: Gtk.CheckButton) -> None:
        enabled = button.get_active()
        for value in self.brightness_values.values():
            value.set_sensitive(enabled)
        for apply_button in self.brightness_apply_buttons.values():
            apply_button.set_sensitive(enabled)

    def _apply_brightness_preview(self, _button: Gtk.Button, profile: str) -> None:
        percent = self.brightness_values[profile].get_value_as_int()
        try:
            set_brightness(percent)
        except (BrightnessError, ValueError) as error:
            self._message(
                "Could not change display brightness",
                str(error),
                Gtk.MessageType.ERROR,
            )
            return
        active_note = (
            " This is the active profile."
            if profile == self._active_profile
            else " Save the value for the next time this profile becomes active."
        )
        self.brightness_profile_status.set_text(
            f"Applied {percent}% from {PROFILE_LABELS[profile]}.{active_note}"
        )

    def _check_for_updates(self, _button: Gtk.Button) -> None:
        self._available_update = None
        self._update_uri = None
        self.update_check_button.set_sensitive(False)
        self.update_action_button.hide()
        self.update_check_status.set_text("Checking the official GitHub release…")
        worker = threading.Thread(target=self._check_for_updates_worker, daemon=True)
        worker.start()

    def _check_for_updates_worker(self) -> None:
        try:
            info = check_for_update(__version__)
        except UpdateCheckError as error:
            GLib.idle_add(self._finish_update_check, None, str(error))
        else:
            GLib.idle_add(self._finish_update_check, info, None)

    def _finish_update_check(
        self, info: UpdateInfo | None, error: str | None
    ) -> bool:
        self.update_check_button.set_sensitive(True)
        if error is not None:
            self.update_check_status.set_text(error)
            return GLib.SOURCE_REMOVE
        if info is None:
            self.update_check_status.set_text("The update check returned no result.")
            return GLib.SOURCE_REMOVE
        if not info.available:
            self.update_check_status.set_text(f"PowerSifu {__version__} is up to date.")
            return GLib.SOURCE_REMOVE

        self.update_check_status.set_text(
            f"PowerSifu {info.latest_version} is available."
        )
        if info.download_url and info.download_sha256 and info.download_size:
            self._available_update = info
            self.update_action_button.set_label(f"Install {info.latest_version}")
        else:
            self._update_uri = info.release_url
            self.update_action_button.set_label(f"Open {info.latest_version} release")
        self.update_action_button.show()
        return GLib.SOURCE_REMOVE

    def _update_action(self, _button: Gtk.Button) -> None:
        if self._available_update is not None:
            info = self._available_update
            self.update_check_button.set_sensitive(False)
            self.update_action_button.set_sensitive(False)
            self.update_check_status.set_text(
                f"Downloading and verifying PowerSifu {info.latest_version}…"
            )
            worker = threading.Thread(
                target=self._install_update_worker,
                args=(info,),
                daemon=True,
            )
            worker.start()
            return
        if self._update_uri is None:
            return
        try:
            Gio.AppInfo.launch_default_for_uri(self._update_uri, None)
        except GLib.Error as error:
            self._message("Could not open the update", str(error), Gtk.MessageType.ERROR)

    def _install_update_worker(self, info: UpdateInfo) -> None:
        package_path = None
        try:
            package_path = download_update(info)
            GLib.idle_add(self._show_installing_update, info.latest_version)
            install_update(package_path)
        except UpdateInstallError as error:
            GLib.idle_add(self._finish_update_install, info.latest_version, str(error))
        else:
            GLib.idle_add(self._finish_update_install, info.latest_version, None)
        finally:
            if package_path is not None:
                package_path.unlink(missing_ok=True)

    def _show_installing_update(self, version: str) -> bool:
        self.update_check_status.set_text(
            f"Installing PowerSifu {version}… Approve the system authentication prompt."
        )
        return GLib.SOURCE_REMOVE

    def _finish_update_install(self, version: str, error: str | None) -> bool:
        self.update_check_button.set_sensitive(True)
        self.update_action_button.set_sensitive(True)
        if error is not None:
            self.update_check_status.set_text("The update was not installed.")
            self._message("Could not install the update", error, Gtk.MessageType.ERROR)
            return GLib.SOURCE_REMOVE

        self._available_update = None
        self._update_uri = None
        self.update_action_button.hide()
        self.update_check_status.set_text(
            f"PowerSifu {version} is installed. Quit and reopen PowerSifu to use it."
        )
        self._message(
            "Update installed",
            f"PowerSifu {version} is ready. Quit and reopen the app to finish updating.",
            Gtk.MessageType.INFO,
        )
        return GLib.SOURCE_REMOVE

    def _apply_source(self, _button: Gtk.Button) -> None:
        self._save(_button)

    def _selected(self, view: Gtk.TreeView) -> Gtk.TreeIter | None:
        _model, tree_iter = view.get_selection().get_selected()
        return tree_iter

    def _toggle_rule(self, _renderer: Gtk.CellRendererToggle, path: str) -> None:
        self.rules_model[path][0] = not self.rules_model[path][0]

    def _toggle_schedule(self, _renderer: Gtk.CellRendererToggle, path: str) -> None:
        self.schedules_model[path][0] = not self.schedules_model[path][0]

    def _add_rule(self) -> None:
        dialog = RuleDialog(self)
        if dialog.run() == Gtk.ResponseType.OK:
            value = dialog.value()
            if self._valid_rule(value):
                self.rules_model.append([value["enabled"], value["process"], value["profile"]])
        dialog.destroy()

    def _edit_rule(self) -> None:
        tree_iter = self._selected(self.rules_view)
        if tree_iter is None:
            return
        row = self.rules_model[tree_iter]
        dialog = RuleDialog(
            self,
            {"enabled": row[0], "process": row[1], "profile": row[2]},
        )
        if dialog.run() == Gtk.ResponseType.OK:
            value = dialog.value()
            if self._valid_rule(value):
                row[0], row[1], row[2] = value["enabled"], value["process"], value["profile"]
        dialog.destroy()

    def _valid_rule(self, value: dict[str, Any]) -> bool:
        if validate_process_name(value["process"]):
            return True
        self._message(
            "Invalid process name",
            "Use an exact executable name with letters, numbers, dots, underscores, plus signs, "
            "@ signs, or hyphens. Core desktop processes cannot be targeted.",
            Gtk.MessageType.WARNING,
        )
        return False

    def _remove_rule(self) -> None:
        tree_iter = self._selected(self.rules_view)
        if tree_iter is not None:
            self.rules_model.remove(tree_iter)

    def _add_schedule(self) -> None:
        dialog = ScheduleDialog(self)
        if dialog.run() == Gtk.ResponseType.OK:
            self._append_schedule(dialog.value())
        dialog.destroy()

    def _edit_schedule(self) -> None:
        tree_iter = self._selected(self.schedules_view)
        if tree_iter is None:
            return
        row = self.schedules_model[tree_iter]
        dialog = ScheduleDialog(
            self,
            {
                "enabled": row[0],
                "label": row[1],
                "time": row[2],
                "days": list(row[5]),
                "profile": row[4],
            },
        )
        if dialog.run() == Gtk.ResponseType.OK:
            value = dialog.value()
            if value["days"]:
                row[0], row[1], row[2], row[3], row[4], row[5] = (
                    value["enabled"],
                    value["label"],
                    value["time"],
                    format_days(value["days"]),
                    value["profile"],
                    value["days"],
                )
            else:
                self._no_days_message()
        dialog.destroy()

    def _append_schedule(self, value: dict[str, Any]) -> None:
        if not value["days"]:
            self._no_days_message()
            return
        self.schedules_model.append(
            [
                value["enabled"],
                value["label"],
                value["time"],
                format_days(value["days"]),
                value["profile"],
                value["days"],
            ]
        )

    def _no_days_message(self) -> None:
        self._message("Select at least one day", "The schedule needs a day to run.", Gtk.MessageType.WARNING)

    def _remove_schedule(self) -> None:
        tree_iter = self._selected(self.schedules_view)
        if tree_iter is not None:
            self.schedules_model.remove(tree_iter)

    def _message(self, title: str, body: str, message_type: Gtk.MessageType) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(body)
        dialog.run()
        dialog.destroy()
