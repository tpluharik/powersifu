# Development

## Requirements

- Python 3.10 or newer
- PyGObject and GTK 3
- Ayatana AppIndicator introspection bindings
- `power-profiles-daemon`
- `brightnessctl` for optional brightness automation
- `dpkg-deb` for packaging

On Ubuntu or Debian:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 power-profiles-daemon brightnessctl dpkg-dev
```

## Run from the checkout

```bash
PYTHONPATH=src python3 -m powersifu
```

Use `--background` to start without opening the settings window. Installed builds detach from the
calling terminal by default; use `--foreground` to keep startup errors visible while debugging.

## Test

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
./tests/test_launcher.sh
python3 -m compileall -q src
```

The tests use only the Python standard library. Hardware, process, and network actions are
mocked, so the suite does not change the active profile or brightness or contact GitHub.

## Build the package

```bash
./packaging/build-deb.sh
```

The package is written to `dist/`. The build uses a temporary staging directory and
`dpkg-deb --root-owner-group`, so it does not require root privileges.
