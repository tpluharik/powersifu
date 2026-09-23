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

Brightness values are limited to 1–100 percent and passed as a fixed argument to
`brightnessctl`. PowerSifu does not accept a device path or command from the user and does not
install privilege rules. Brightness automation is disabled by default.

## Update checks

Update checks run only after the user clicks **Check for updates**. Responses are size-limited,
and release/download links must use HTTPS on GitHub-owned hosts. PowerSifu opens the official
release or `.deb` in the desktop handler; it never installs packages or escalates privileges.

## Reporting a vulnerability

Open a private GitHub security advisory in the repository. Do not include secrets or personally
identifying process information in a public issue.
