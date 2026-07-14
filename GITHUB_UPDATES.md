# GitHub Releases Updates

The update system is included but remains inactive until a repository is configured.

In **Settings**, enter the repository as:

```text
owner/repository
```

The included GitHub Actions workflow builds the Windows application when a `v*` tag is pushed. It publishes:

```text
Stories_Of_Yggdrasil_OSC_Windows_<tag>.zip
Stories_Of_Yggdrasil_OSC_Windows_<tag>.zip.sha256
```

The desktop client:

1. Checks the repository's latest release.
2. Shows the new version and release notes.
3. Asks before downloading.
4. Verifies the SHA-256 file when one is present.
5. Asks again before closing and installing.
6. Restarts the updated program.

No update is downloaded or installed without user confirmation.
