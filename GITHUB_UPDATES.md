# GitHub release notes

Repository:

```text
StarhunterUC/Stories-Of-Yggdrasil-OSC
```

For Desktop v0.8.11:

```powershell
git status
git add .
git commit -m "Stories Of Yggdrasil OSC v0.8.11"
git push origin main

git tag -a v0.8.11 -m "Stories Of Yggdrasil OSC v0.8.11"
git push origin v0.8.11
```

The GitHub workflow runs the full unit-test suite, builds the Windows executable, and publishes the release ZIP with a SHA-256 checksum.

Desktop v0.8.11 requires OSC API v0.8.13. Deploy `server_companion/UPLOAD_AND_DEPLOY.ps1` after v0.8.13 verification to expose the optional v0.8.14 attacker roster.
