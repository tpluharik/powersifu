"""Power source, schedule, and application-rule automation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from .config import ConfigStore
from .power import PowerProfileError, get_active_profile, on_ac_power, set_profile
from .processes import stop_application
from .scheduler import schedule_key, schedule_matches


NotifyCallback = Callable[[str, str], None]
StateCallback = Callable[[str, bool], None]


class AutomationEngine:
    def __init__(
        self,
        store: ConfigStore,
        notify: NotifyCallback | None = None,
        state_changed: StateCallback | None = None,
    ) -> None:
        self.store = store
        self.notify = notify or (lambda _title, _body: None)
        self.state_changed = state_changed or (lambda _profile, _on_ac: None)
        self.last_source: bool | None = None
        self.last_profile: str | None = None
        self.fired_schedules: dict[str, datetime] = {}
        self.last_error: str | None = None

    def tick(self, force_source: bool = False, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        on_ac = on_ac_power()
        automation = self.store.data["automation"]
        source_changed = self.last_source is not None and on_ac != self.last_source

        try:
            active = get_active_profile()
            if automation["enabled"] and (force_source or source_changed):
                target = automation["ac_profile"] if on_ac else automation["battery_profile"]
                if target != active:
                    self.apply_profile(target, "AC adapter connected" if on_ac else "Running on battery")
                    active = target

            if active != self.last_profile:
                self._run_application_rules(active)
                self.last_profile = active

            for index, schedule in enumerate(self.store.data["schedules"]):
                key = schedule_key(index, now)
                if schedule_matches(schedule, now) and key not in self.fired_schedules:
                    self.apply_profile(schedule["profile"], schedule.get("label") or "Scheduled change")
                    active = schedule["profile"]
                    self.fired_schedules[key] = now

            cutoff = now - timedelta(days=2)
            self.fired_schedules = {
                key: fired for key, fired in self.fired_schedules.items() if fired >= cutoff
            }
            self.last_error = None
        except (PowerProfileError, OSError) as error:
            message = str(error)
            if message != self.last_error:
                self.notify("PowerSifu needs attention", message)
            self.last_error = message

        self.last_source = on_ac
        self.state_changed(self.last_profile or "unknown", on_ac)
        return True

    def apply_profile(self, profile: str, reason: str) -> None:
        set_profile(profile)
        self.last_profile = profile
        self._run_application_rules(profile)
        self.notify("Power profile changed", f"{profile} — {reason}")
        self.state_changed(profile, on_ac_power())

    def apply_current_source(self) -> None:
        self.tick(force_source=True)

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
