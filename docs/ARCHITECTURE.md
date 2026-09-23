# Architecture

PowerSifu is a single-user GTK application that stays alive through its tray indicator. It has
no privileged daemon and no network service.

## Components

- `config.py` owns the versioned JSON configuration and XDG autostart override.
- `power.py` reads Linux power-supply state and calls `powerprofilesctl`.
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
or another tool—evaluates application rules. Schedules are checked in the same tick and guarded
against duplicate execution within a minute.

## Trust boundary

PowerSifu runs entirely as the logged-in user. The existing power-profiles system service owns
hardware changes. Process rules cannot contain arguments, paths, regular expressions, or shell
syntax, which keeps their effect narrow and reviewable.
