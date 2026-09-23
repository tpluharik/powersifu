# Security

## Application-stop rules

PowerSifu deliberately does not accept shell commands. A rule contains only an exact process
name and a power profile. When the profile becomes active, PowerSifu scans `/proc`, selects
exact name matches owned by the current user, and sends `SIGTERM`.

The following process classes are protected and cannot be configured: the desktop shell,
display servers, the user service manager, D-Bus, and the desktop audio stack. PowerSifu also
never sends a signal to its own process and never escalates privileges to stop applications.

## Power-profile changes

Profile switching is delegated to the system's `power-profiles-daemon` through
`powerprofilesctl`. Distribution policy controls whether an authentication prompt is required.
PowerSifu does not install custom privilege rules.

## Brightness control

Brightness values are limited to 1–100 percent. On GNOME, PowerSifu updates the shell's existing
brightness slider through the per-user accessibility bus and the built-in backlight through
Mutter's session service. Other desktops receive a fixed percentage argument through
`brightnessctl`. PowerSifu does not inspect or change application content, accept a device path or
command from the user, or install privilege rules. Brightness automation is disabled by default.

## Update checks

Update checks run only after the user clicks **Check for updates**. Responses and downloads are
size-limited, redirects must remain on GitHub-owned HTTPS hosts, and the asset filename must match
the advertised version. The downloaded byte count and SHA-256 digest must match GitHub's release
metadata. Before installation, PowerSifu uses `dpkg-deb` to verify the package name, version, and
architecture.

Installation starts only after the user clicks **Install update**. PowerSifu invokes the fixed
argument sequence `pkexec apt-get install --yes <verified-package>` without a shell or
user-provided command. The operating system displays its authentication dialog and controls
authorization; cancellation leaves the installed version unchanged. PowerSifu installs no custom
privilege rules and removes the cached package after the attempt.

## Reporting a vulnerability

Open a private GitHub security advisory in the repository. Do not include secrets or personally
identifying process information in a public issue.
