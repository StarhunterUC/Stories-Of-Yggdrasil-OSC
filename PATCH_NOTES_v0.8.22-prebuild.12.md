# v0.8.22-prebuild.12 — Windows Update Extraction Hardening

Fixes installer progress checkpoint file collisions on Windows, with short retries. Uses the dedicated GUID staging directory to tolerate duplicate regular ZIP file entries during extraction, retaining path escape, symbolic-link, archive size, checksum, application version, and restart checks. Also includes the previous `.11` dynamic Active Effects and NPC profile UI changes.

For users stuck on `.11` installation due to an older updater, download and extract `.12` into a **new clean folder** from the GitHub release, exit OSC completely, and run the executable there. Do not delete `%APPDATA%/StoriesOfYggdrasil/OSCContactSystem`; it stores pairing and logs.
