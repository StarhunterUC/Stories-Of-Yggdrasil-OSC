# v0.8.22-prebuild.5 — Installer restart hang repair

Fixes the updater freezing at **Preparing restart** (92%) after copying a new release, with no `update_result.json` and a Windows Not Responding window. The former installer relied on a PowerShell `Start-Job` that could remain active after verification.

- Use a separately monitored PowerShell process instead of `Start-Job` / `Receive-Job`.
- Clear stale progress and per-worker outcome files before each attempt.
- Write atomic progress checkpoints and require an explicit worker success result.
- Apply an 180-second per-phase stall limit; keep the Windows progress UI pumping messages.
- Verify the installed executable/version again before launch and log the restart PID.
- Do not perform recursive temporary staging cleanup on the UI thread.

**Recovery:** Existing versions (.4 or older) still contain their original updater. If it hangs, safely stop the inactive installer after confirming the release executable and version metadata, then install this prerelease manually from the ZIP. Avoid layering installations while any worker/robocopy is active.

No changes to VPS, Unity Tool, or combat calculations. Stable v0.8.21 remains unchanged.
