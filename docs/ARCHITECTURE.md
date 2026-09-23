# Architecture

PowerSifu is a single-user GTK application that stays alive through its tray indicator. It has
no privileged daemon and no network service.

## Components

- `config.py` owns the versioned JSON configuration and XDG autostart override.
- `power.py` reads Linux power-supply state and calls `powerprofilesctl`.
- `brightness.py` validates percentages, calls `brightnessctl`, and falls back to Mutter's
  per-user display API when direct backlight access is restricted.
- `updates.py` performs bounded GitHub release checks and downloads, validates Debian package
  identity, and requests authenticated installation through the system package manager.
- `scheduler.py` matches enabled recurring weekly schedules once per minute.
- `processes.py` performs exact-name, same-user process discovery and graceful termination.
- `engine.py` coordinates power-source changes, external profile changes, schedules, and rules.
- `ui.py` provides the GTK settings window and rule editors.
- `app.py` owns the application lifecycle, notifications, timer, and tray menu.

The configuration is stored at `${XDG_CONFIG_HOME:-~/.config}/powersifu/config.json` with mode
`0600`. Writes use a temporary file and atomic replacement.

## Event model

Every five seconds the engine checks the AC adapter and active profile. A source change can apply
the configured AC or battery profile. A profile change—whether caused by PowerSifu, the desktop,
or another tool—applies configured brightness and evaluates application rules. Schedules are
checked in the same tick and guarded against duplicate execution within a minute.

## Trust boundary

PowerSifu runs entirely as the logged-in user. The existing power-profiles system service owns
profile changes. Brightness is delegated to the desktop session or `brightnessctl`. Process rules cannot contain
arguments, paths, regular expressions, or shell syntax, which keeps their effect narrow and
reviewable. Update checks and installs are user-initiated, size limited, and accept only HTTPS URLs
on GitHub-owned hosts. Packages must match GitHub's size and SHA-256 metadata plus the expected
Debian name, version, and architecture before a fixed `pkexec apt-get` invocation requests
system authentication.
