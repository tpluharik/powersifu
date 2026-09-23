# Changelog

All notable changes to PowerSifu are documented here.

## 0.3.0 — 2026-09-23

- Added authenticated installation of official updates directly from the About page.
- Downloads are size-limited, restricted to GitHub-owned HTTPS hosts, and SHA-256 verified.
- Debian package name, version, and architecture are verified before privilege escalation.
- Package-manager and authentication errors are reported inside the application.

## 0.2.3 — 2026-09-23

- Added a GNOME session fallback for systems that deny direct `brightnessctl` writes.
- Brightness failures are now shown in the settings window instead of being followed by success.
- Restricted `brightnessctl` operations explicitly to backlight devices.

## 0.2.2 — 2026-09-23

- Fixed a settings-window startup crash caused by the update-status label shadowing a method.
- Added a regression test that prevents GTK widget fields from shadowing window methods.

## 0.2.1 — 2026-09-23

- Launches as a standalone desktop process without remaining attached to a terminal.
- Added an explicit `--foreground` troubleshooting mode.

## 0.2.0 — 2026-09-23

- Added optional display-brightness percentages for each power profile.
- Added an opt-in GitHub release checker and official `.deb` download action.
- Added configuration migration, error handling, tests, and updated packaging.

## 0.1.0 — 2026-09-23

- Added GTK configuration window and Ayatana AppIndicator tray menu.
- Added automatic AC/battery power-profile switching.
- Added recurring weekly profile schedules.
- Added exact-name, same-user application stop rules per profile.
- Added XDG autostart support, notifications, Debian packaging, tests, and documentation.
