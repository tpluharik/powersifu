# Architecture

PowerSifu is a single-user GTK application that stays alive through its tray indicator. It has
no privileged daemon and no network service.

## Components

- `config.py` owns the versioned JSON configuration and XDG autostart override.
- `power.py` keeps persistent system D-Bus proxies for power-profiles-daemon and UPower, consumes
  property-change events, and provides a sysfs fallback for power-source detection.
- `brightness.py` validates percentages, drives GNOME Shell's global slider through the desktop
  accessibility bus, and falls back to Mutter or `brightnessctl` when needed.
- `updates.py` performs bounded GitHub release checks and downloads, validates Debian package
  identity, and requests authenticated installation through the system package manager.
- `scheduler.py` matches enabled recurring weekly schedules once per minute.
- `processes.py` performs exact-name, same-user process discovery and graceful termination.
- `engine.py` coordinates power-source changes, external profile changes, schedules, and rules.
- `ui.py` provides the GTK settings window and rule editors.
- `app.py` owns the application lifecycle, notifications, event subscriptions, safety timer,
  schedule timer, and tray menu.

The configuration is stored at `${XDG_CONFIG_HOME:-~/.config}/powersifu/config.json` with mode
`0600`. Writes use a temporary file and atomic replacement.

## Event model

UPower source changes and power-profiles-daemon profile changes arrive through cached D-Bus proxy
signals. The relevant state is passed directly into the engine without an extra service query. A
60-second fresh reconciliation provides recovery after a missed signal or service restart.

A source change can apply the configured AC or battery profile. A profile change—whether caused by
PowerSifu, the desktop, or another tool—applies configured brightness and evaluates application
rules. Enabled schedules use a separate timer aligned to the next wall-clock minute and remain
unscheduled when none are enabled. Duplicate execution within one minute is still prevented.

On GNOME, brightness application is deliberately two-part. AT-SPI updates the shell's global
Quick Settings slider, while Mutter's session D-Bus service sets the physical built-in-display
backlight. This keeps GNOME's global control, per-display control, and hardware value aligned.

## Trust boundary

PowerSifu runs entirely as the logged-in user. The existing power-profiles system service owns
profile changes. Brightness is delegated to the desktop session or `brightnessctl`. Process rules
cannot contain arguments, paths, regular expressions, or shell syntax, which keeps their effect
narrow and reviewable. Update checks and installs are user-initiated, size limited, and accept only
HTTPS URLs on GitHub-owned hosts. Packages must match GitHub's size and SHA-256 metadata plus the
expected Debian name, version, and architecture before a fixed `pkexec apt-get` invocation requests
system authentication.
