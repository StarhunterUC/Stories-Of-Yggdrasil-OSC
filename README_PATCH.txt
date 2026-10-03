Stories Of Yggdrasil OSC Desktop v0.8.20 — WinHTTP / Schannel Repair

Purpose:
- v0.8.19 still used Python/OpenSSL for the actual HTTPS socket path.
- v0.8.20 sends Sam.py API traffic through Windows WinHTTP + Schannel directly.
- This matches the native Windows TLS stack that already succeeds on the affected PC.

Security:
- HTTPS required.
- Certificate validation remains enabled.
- Hostname validation remains enabled.
- TLS 1.2 required on the Windows native path.
- Sam.py authenticated requests do not follow redirects.
- No verify=False / unverified context is used.

Apply from PowerShell:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
  & ".\APPLY_V0820_WINHTTP_SCHANNEL.ps1" -RepoRoot "C:\path\to\Stories-Of-Yggdrasil-OSC-Git-v0.8.11" -Build

Sam.py is not changed by this patch.
