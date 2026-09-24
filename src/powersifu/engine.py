"""Power source, schedule, brightness, and application-rule automation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from .brightness import BrightnessError, set_brightness
from .config import ConfigStore
from .power import PowerProfileError, get_active_profile, on_ac_power, set_profile
from .processes import stop_application
from .scheduler import schedule_key, schedule_matches


NotifyCallback = Callable[[str, str], None]
StateCallback = Callable[[str, bool], None]


class _DefaultPowerBackend:
    """Keep the function API patchable for tests and non-GTK callers."""

    def get_active_profile(self, *, refresh: bool = False) -> str:
        return get_active_profile()

    def get_on_ac_power(self, *, refresh: bool = False) -> bool:
        return on_ac_power()

    def set_profile(self, profile: str) -> None:
        set_profile(profile)


class AutomationEngine:
    def __init__(
        self,
        store: ConfigStore,
        notify: NotifyCallback | None = None,
        state_changed: StateCallback | None = None,
        power: Any | None = None,
    ) -> None:
        self.store = store
        self.notify = notify or (lambda _title, _body: None)
        self.state_changed = state_changed or (lambda _profile, _on_ac: None)
        self.power = power or _DefaultPowerBackend()
        self.last_source: bool | None = None
        self.last_profile: str | None = None
        self.fired_schedules: dict[str, datetime] = {}
        self.last_error: str | None = None
        self.last_brightness_error: str | None = None

    def tick(
        self,
        force_source: bool = False,
        active_profile: str | None = None,
        on_ac_state: bool | None = None,
        refresh: bool = False,
    ) -> bool:
        on_ac = self.last_source if self.last_source is not None else False
        automation = self.store.data["automation"]

        try:
            on_ac = (
                self.power.get_on_ac_power(refresh=refresh)
                if on_ac_state is None
                else on_ac_state
            )
            active = (
                self.power.get_active_profile(refresh=refresh)
                if active_profile is None
                else active_profile
            )
            source_changed = self.last_source is not None and on_ac != self.last_source
            if automation["enabled"] and (force_source or source_changed):
                target = automation["ac_profile"] if on_ac else automation["battery_profile"]
                if target != active:
                    self.apply_profile(target, "AC adapter connected" if on_ac else "Running on battery")
                    active = target

            if active != self.last_profile:
                self._run_profile_actions(active)
                self.last_profile = active
            elif force_source:
                # Saving settings should apply a changed brightness value immediately,
                # without re-running application stop rules.
                self._apply_brightness(active)
            self.last_error = None
        except (PowerProfileError, OSError) as error:
            message = str(error)
            if message != self.last_error:
                self.notify("PowerSifu needs attention", message)
            self.last_error = message

        self.last_source = on_ac
        self.state_changed(self.last_profile or "unknown", on_ac)
        return True

    def run_schedules(self, now: datetime | None = None) -> bool:
        """Evaluate schedules once near the wall-clock minute boundary."""

        schedules = self.store.data["schedules"]
        if not schedules:
            return False
        now = now or datetime.now()
        fired = False
        try:
            for index, schedule in enumerate(schedules):
                key = schedule_key(index, now)
                if schedule_matches(schedule, now) and key not in self.fired_schedules:
                    self.apply_profile(
                        schedule["profile"],
                        schedule.get("label") or "Scheduled change",
                    )
                    self.fired_schedules[key] = now
                    fired = True

            cutoff = now - timedelta(days=2)
            self.fired_schedules = {
                key: fired_at
                for key, fired_at in self.fired_schedules.items()
                if fired_at >= cutoff
            }
            self.last_error = None
        except (PowerProfileError, OSError) as error:
            message = str(error)
            if message != self.last_error:
                self.notify("PowerSifu needs attention", message)
            self.last_error = message
        return fired

    def apply_profile(self, profile: str, reason: str) -> None:
        previous_profile = self.last_profile
        self.last_profile = profile
        try:
            self.power.set_profile(profile)
        except (PowerProfileError, OSError, ValueError):
            self.last_profile = previous_profile
            raise
        self._run_profile_actions(profile)
        self.notify("Power profile changed", f"{profile} — {reason}")
        self.state_changed(profile, self.power.get_on_ac_power())

    def apply_current_source(self) -> None:
        self.tick(force_source=True, refresh=True)

    def _run_profile_actions(self, profile: str) -> None:
        self._apply_brightness(profile)
        self._run_application_rules(profile)

    def _apply_brightness(self, profile: str) -> None:
        settings = self.store.data["brightness"]
        if not settings["enabled"]:
            self.last_brightness_error = None
            return

        percent = settings["profiles"][profile]
        try:
            set_brightness(percent)
        except (BrightnessError, ValueError) as error:
            message = str(error)
            if message != self.last_brightness_error:
                self.notify("Could not change display brightness", message)
            self.last_brightness_error = message
        else:
            self.last_brightness_error = None

    def _run_application_rules(self, profile: str) -> None:
        for rule in self.store.data["application_rules"]:
            if not rule.get("enabled", True) or rule.get("profile") != profile:
                continue
            stopped = stop_application(rule.get("process", ""))
            if stopped:
                count = len(stopped)
                self.notify(
                    "Application stopped",
                    f"{rule['process']}: terminated {count} process{'es' if count != 1 else ''}",
                )
