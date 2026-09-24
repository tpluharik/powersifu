# Changelog

All notable changes to PowerSifu are documented here.

## 0.3.4 — 2026-09-24

- Switched profile reads and writes to power-profiles-daemon's system D-Bus interface.
- Avoided repeated `powerprofilesctl` processes and their Python 3.14 shutdown crash.
- Added regression tests for profile validation and direct service operations.

## 0.3.3 — 2026-09-23

- Changed GNOME's global Quick Settings brightness slider directly through the desktop session.
- Kept the main slider, per-display slider, and physical backlight synchronized.
- Retained Mutter and `brightnessctl` fallbacks for unsupported desktop environments.

## 0.3.2 — 2026-09-23

- Changed GNOME brightness through the desktop session before using `brightnessctl`.
- Kept GNOME's Quick Settings brightness slider synchronized with profile changes.
- Retained `brightnessctl` as the fallback for other Linux desktops.

## 0.3.1 — 2026-09-23

- Marked the currently active power profile in the Brightness tab.
- Added an **Apply now** button for every profile to preview brightness immediately.
- Added clear feedback showing which profile value was applied.

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
