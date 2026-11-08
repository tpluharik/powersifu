# Security

## Application-stop rules

PowerSifu deliberately does not accept shell commands. A rule contains only an exact process
name and a power profile. When the profile becomes active, PowerSifu scans `/proc`, selects
exact name matches owned by the current user, and sends `SIGTERM`.

The following process classes are protected and cannot be configured: the GNOME, KDE, Unity,
XFCE, LXQt, MATE, and Cinnamon session components advertised by the autostart entry; display
servers; the user service manager; D-Bus; and the desktop audio stack. PowerSifu also never sends a
signal to its own process or a session leader. It rechecks identity immediately before signalling
and uses Linux PID descriptors when available to avoid PID-reuse races. Process stopping never
escalates privileges.

## Power-profile changes

Profile switching is delegated directly to the system's `power-profiles-daemon` over its system
D-Bus interface. Distribution policy controls whether an authentication prompt is required.
Profile switching does not use PowerSifu's privileged update helper or authorization policy.

## Brightness control

Brightness values are limited to 1–100 percent. On GNOME, PowerSifu updates the shell's existing
brightness slider through the per-user accessibility bus and the built-in backlight through
Mutter's session service. Other desktops receive a fixed percentage argument through
`brightnessctl`. PowerSifu does not inspect or change application content, accept a device path or
command from the user, or install privilege rules. Brightness automation is disabled by default.

## Update checks

Update checks run only after the user clicks **Check for updates**. Responses and downloads are
size-limited, redirects must remain on GitHub-owned HTTPS hosts, and all asset filenames must match
the advertised version. Downloads prefer GitHub's anonymous release-asset API and accept API paths
only for numeric asset identifiers in the exact `tpluharik/powersifu` repository. The conventional
release URL is retained as a transport-failure fallback. Installation requires a canonical manifest
signed by PowerSifu's Ed25519 release key. The manifest binds the package name, version,
architecture, byte count, and SHA-256 digest. Before elevation, PowerSifu authenticates the manifest
and uses `dpkg-deb` to verify the package name, version, and architecture.

Installation starts only after the user clicks **Install update**. PowerSifu invokes only the fixed,
root-owned `powersifu-update-helper` through `pkexec`. The helper treats every supplied path as
untrusted: it rejects links and non-regular files, copies from open file descriptors into a
root-owned transaction directory, and independently repeats signature, digest, package-identity,
and version checks. It rejects downgrades before invoking a fixed absolute `apt-get` path on the
protected copy. The dedicated polkit action requires active administrator authentication and does
not retain authorization. Cancellation leaves the installed version unchanged, and staging data is
removed after every attempt.

## Reporting a vulnerability

Open a private GitHub security advisory in the repository. Do not include secrets or personally
identifying process information in a public issue.
