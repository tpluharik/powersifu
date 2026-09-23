# PowerSifu

![PowerSifu lightning and power-button icon](assets/icons/hicolor/128x128/apps/powersifu.png)

PowerSifu is a small Linux desktop utility that keeps power-profile policy in one place. It runs
in the system tray, automatically switches profiles when AC power changes, applies recurring
weekly schedules, and can gracefully stop selected applications when a profile becomes active.

The first release targets Ubuntu and Debian desktops using
[`power-profiles-daemon`](https://gitlab.freedesktop.org/upower/power-profiles-daemon).

## Features

- **AC/battery automation:** choose independent profiles for plugged-in and battery use.
- **Tray control:** view the current source/profile and switch profiles without opening settings.
- **Recurring schedules:** choose a time, one or more weekdays, and a target profile.
- **Application rules:** stop exact same-user process names when Power Saver, Balanced, or
  Performance becomes active.
- **Startup integration:** runs quietly at login and can be disabled from the GUI.
- **Desktop notifications:** reports profile changes, stopped applications, and actionable errors.
- **Safe by construction:** no arbitrary commands, no root process termination, and protected
  desktop processes.

## Install

Download or build `powersifu_0.1.0_all.deb`, then install it with:

```bash
sudo apt install ./dist/powersifu_0.1.0_all.deb
```

Launch **PowerSifu** from the application menu. The package also starts it in the tray on future
logins. On Ubuntu, tray support is available through the default AppIndicator integration. Other
GNOME distributions may need the AppIndicator extension recommended by the package.

To uninstall:

```bash
sudo apt remove powersifu
```

Your user configuration remains in `~/.config/powersifu/` unless you remove it separately.

## Configure PowerSifu

### General

The default policy is:

| Power source | Profile |
| --- | --- |
| Plugged in | Balanced |
| Battery | Power Saver |

Open the tray menu and choose **Settings** to change either target, disable source automation, or
control startup. **Apply current source rule now** immediately evaluates the saved policy.

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

PowerSifu checks power state every five seconds. It delegates hardware control to the installed
`power-profiles-daemon`; it does not install a privileged daemon or custom authorization policy.

## Build from source

Install development dependencies on Ubuntu/Debian:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 power-profiles-daemon dpkg-dev
```

Run tests and build the package:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src
./packaging/build-deb.sh
```

The resulting `.deb` is placed in `dist/`. The same test-and-build flow runs in GitHub Actions.
See [development notes](docs/DEVELOPMENT.md) and the [architecture overview](docs/ARCHITECTURE.md)
for implementation details.

## Troubleshooting

**The tray icon is missing:** verify that an AppIndicator implementation is enabled. Ubuntu ships
one by default; other GNOME installations may need `gnome-shell-extension-appindicator`.

**A profile does not change:** run `powerprofilesctl list` and confirm that the requested profile
is available. Your distribution may display an authorization prompt for profile changes.

**An application rule does nothing:** process matching is exact. Confirm the name with the `ps`
command above. Wrapper applications may use a different executable name than their desktop label.

**Schedules do not run:** PowerSifu must be running in the tray, and the selected day/time uses
the system's current local timezone.

## License

PowerSifu is available under the [MIT License](LICENSE).
