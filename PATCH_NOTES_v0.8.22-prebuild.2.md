# v0.8.22-prebuild.2 — Privacy-first crash diagnostics and installer responsiveness

This is a TEST BUILD on Protocol 21 / Unity Tool TB18, continuing v0.8.22-prebuild.1. Stable v0.8.21 is unchanged.

## Crash reports
- Local-only, allowlisted JSON crash reports for Desktop exceptions, unexpected termination and main-thread stalls (25-second watchdog).
- A separate watchdog process continues operating when the Tk UI is unresponsive.
- Installer failures and stalled installation phases generate local-only crash reports.
- Settings → Privacy & Crash Reports: sharing is **off by default**. Users review individual reports, copy the exact contents, delete reports, or explicitly send one to a configured first-party receiver.
- No Discord/VRChat IDs, character names, pairing credentials, IP addresses, raw logs, exception messages, or personal file paths are part of the report schema.
- Network delivery is inactive unless the first-party receiver endpoint is deployed and configured; opt-in alone NEVER sends anything.
- The receiver will see the connecting public IP address unless its access logs are configured not to retain it.

## Installer reliability
- Move ZIP extraction/file copy into a background PowerShell job and keep the installer UI pumping Windows messages.
- Record installer stage changes; watchdog detects stalled stages and preserves a sanitized local report.
- Preserve checksum validation, version checks, existing install log, and restart behavior.
- Reports live at %APPDATA%\StoriesOfYggdrasil\OSCContactSystem\crash_reports

## Compatibility
- Desktop: 0.8.22-prebuild.2; Unity Tool: TB18; Protocol 21; restricted OSC API 0.8.19 recommended.
- No combat data, pairing tokens, or existing Sam.py endpoint changes.
- Crash receiver deployment is a separate server operation. Do not send reports to nonexistent routes.
