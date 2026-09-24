# PowerSifu

[![Latest release](https://img.shields.io/github/v/release/tpluharik/powersifu)](https://github.com/tpluharik/powersifu/releases/latest)
[![Build](https://github.com/tpluharik/powersifu/actions/workflows/build.yml/badge.svg)](https://github.com/tpluharik/powersifu/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

![PowerSifu lightning and power-button icon](assets/icons/hicolor/128x128/apps/powersifu.png)

PowerSifu is a small Linux desktop utility that keeps power-profile policy in one place. It runs
in the system tray, automatically switches profiles when AC power changes, applies optional
profile-specific screen brightness, runs weekly schedules, and can gracefully stop selected
applications when a profile becomes active.

PowerSifu targets Ubuntu and Debian desktops using
[`power-profiles-daemon`](https://gitlab.freedesktop.org/upower/power-profiles-daemon).

## Features

- **AC/battery automation:** choose independent profiles for plugged-in and battery use.
- **Event-driven monitoring:** react immediately to source and profile changes without frequent
  background polling.
- **Profile brightness:** assign a 1–100% screen brightness to each profile, with GNOME's
  Quick Settings slider kept synchronized.
- **Tray control:** view the current source/profile and switch profiles without opening settings.
- **Recurring schedules:** choose a time, one or more weekdays, and a target profile.
- **Application rules:** stop exact same-user process names when Power Saver, Balanced, or
  Performance becomes active.
- **Startup integration:** runs quietly at login and can be disabled from the GUI.
- **Desktop notifications:** reports profile changes, stopped applications, and actionable errors.
- **In-app updater:** download, verify, and install official releases with system authentication.
- **Safe by construction:** no arbitrary commands, no root process termination, and protected
  desktop processes.

## Install

Download [PowerSifu 0.3.5 for Ubuntu/Debian](https://github.com/tpluharik/powersifu/releases/download/v0.3.5/powersifu_0.3.5_all.deb),
then install it with:

```bash
sudo apt install ./powersifu_0.3.5_all.deb
```

Launch **PowerSifu** from the application menu. The package also starts it in the tray on future
logins. On Ubuntu, tray support is available through the default AppIndicator integration. Other
GNOME distributions may need the AppIndicator extension recommended by the package.

PowerSifu is a standalone desktop application: launching it from the application menu never opens
a terminal, and running `powersifu` from a shell detaches the app from that shell. For diagnostics,
`powersifu --foreground` keeps it attached so startup errors remain visible.

To uninstall:

```bash
sudo apt remove powersifu
```

Your user configuration remains in `~/.config/powersifu/` unless you remove it separately.

## Update

Open **Settings → About → Check for updates**. When a newer official package is available,
choose **Install update** and approve the operating-system authentication prompt. PowerSifu
verifies the download before installation. Quit and reopen PowerSifu afterward so the running
process loads the new version.

## Configure PowerSifu

### General

The default policy is:

| Power source | Profile |
| --- | --- |
| Plugged in | Balanced |
| Battery | Power Saver |

Open the tray menu and choose **Settings** to change either target, disable source automation, or
control startup. **Apply current source rule now** immediately evaluates the saved policy.

### Display brightness

Open the **Brightness** tab, enable profile brightness, and choose a percentage for Power
Saver, Balanced, and Performance. The setting is applied when a profile activates and when
you save the configuration. On GNOME, PowerSifu changes the desktop's own global brightness
slider, keeping both the visible Quick Settings control and physical backlight synchronized.
Mutter and `brightnessctl` remain safe, unprivileged fallbacks. The feature remains off by default,
and external monitors may require their own controls.

The active profile is marked in the Brightness tab. **Apply now** beside any profile previews that
percentage immediately, making it easy to verify the display response before saving.

### Application rules

Add the exact Linux process name and the profile that should stop it. For example, a rule for
`spotify` on `power-saver` asks every Spotify process owned by the current user to terminate when
Power Saver becomes active.

Find likely process names with:

```bash
ps -u "$USER" -o comm= | sort -u
```

Rules send `SIGTERM`, which gives applications a chance to exit cleanly. They do not force-kill,
restart, or suspend applications. See [SECURITY.md](SECURITY.md) for the complete safety model.

### Schedules

A schedule contains an optional label, 24-hour time, selected weekdays, and target profile. Each
enabled schedule runs at most once per matching minute. Schedules use the laptop's local timezone
and require PowerSifu to be running.

### Tray menu

The tray label shows the active profile. The menu provides immediate manual switching, an
AC/battery automation toggle, settings access, and Quit. A manual profile change also evaluates
application rules.

## Configuration

Settings are saved atomically with user-only permissions at:

```text
${XDG_CONFIG_HOME:-~/.config}/powersifu/config.json
```

PowerSifu listens for power-source and profile-change events through persistent system-service
connections. A 60-second safety reconciliation covers missed or unavailable signals. Schedule
checks run only on wall-clock minute boundaries and sleep completely when no schedule is enabled.
PowerSifu applies optional display changes through the desktop session or `brightnessctl`; it does
not install a privileged daemon or custom authorization policy. The About-page update checker contacts only
the official GitHub Releases API after **Check for updates** is clicked. **Install update**
downloads the official package, verifies its Debian identity and version, and requests
authentication through the operating system before installation. The download's size and SHA-256
digest must also match GitHub's release metadata.

## Build from source

Install development dependencies on Ubuntu/Debian:

```bash
sudo apt install python3-gi gir1.2-glib-2.0 gir1.2-gtk-3.0 gir1.2-atspi-2.0 \
  gir1.2-ayatanaappindicator3-0.1 power-profiles-daemon upower brightnessctl pkexec apt dpkg-dev
```

Run tests and build the package:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src
./packaging/build-deb.sh
```

The resulting `.deb` is placed in `dist/`. The same test-and-build flow runs in GitHub Actions.
See [development notes](docs/DEVELOPMENT.md) and the [architecture overview](docs/ARCHITECTURE.md)
for implementation details. Maintainers can follow the [release checklist](docs/RELEASE.md).

## Troubleshooting

**The tray icon is missing:** verify that an AppIndicator implementation is enabled. Ubuntu ships
one by default; other GNOME installations may need `gnome-shell-extension-appindicator`.

**A profile does not change:** confirm that Power Mode is available in your desktop's system menu
and that `power-profiles-daemon` is running. Your distribution may display an authorization prompt
for profile changes.

**Brightness does not change:** PowerSifu shows the underlying error after saving. On GNOME it
updates both the global Quick Settings slider and Mutter's built-in-display backlight. Other
desktops should provide a working `brightnessctl` setup. External displays may require their own
controls.

**The backlight changes but GNOME's slider does not:** confirm that PowerSifu 0.3.3 or newer is
installed, then quit and reopen the tray application. The Debian package installs the required
AT-SPI binding automatically.

**An update fails:** confirm that GitHub is reachable and approve the system authentication
prompt. PowerSifu verifies the package before requesting installation and reports package-manager
errors in the About tab.

**An application rule does nothing:** process matching is exact. Confirm the name with the `ps`
command above. Wrapper applications may use a different executable name than their desktop label.

**Schedules do not run:** PowerSifu must be running in the tray, and the selected day/time uses
the system's current local timezone.

## License

PowerSifu is available under the [MIT License](LICENSE).
