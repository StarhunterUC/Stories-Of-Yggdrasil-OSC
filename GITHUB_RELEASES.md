# GitHub build and release flow

The Desktop repository uses two GitHub Actions workflows:

- **Desktop CI** runs the repository verifier, tests, and source audit on pushes to `main` and pull requests.
- **Build Windows Release** runs on Windows, builds the PyInstaller application, creates the release ZIP/checksums, uploads a workflow artifact, and can publish a GitHub Release.

## Normal development

Push or open a pull request normally. CI must pass before a release should be created.

## Build without publishing

Open **Actions → Build Windows Release → Run workflow** and leave **Publish release** disabled.

The workflow uploads an artifact named `<tag>-windows`. This is the safe test-build path and does not create a public GitHub Release.

## Publish a release

There are two supported paths:

1. Run **Build Windows Release** manually with **Publish release** enabled. The workflow creates/updates the tag and GitHub Release described by `version.json`.
2. Push the matching tag (for example `v0.8.21`). A matching tag automatically builds and publishes the release.

The tag must match `version.json`; mismatches fail before the executable is built.

## Release metadata

`version.json` is the release source of truth. Existing fields remain supported. New releases should use:

```json
{
  "product": "Stories Of Yggdrasil OSC",
  "repository": "StarhunterUC/Stories-Of-Yggdrasil-OSC",
  "version": "0.8.21",
  "tag": "v0.8.21",
  "channel": "stable",
  "prerelease": false,
  "api_minimum": "0.8.13",
  "api_recommended": "0.8.18",
  "unity_tool": "0.5.10-TB16",
  "osc_protocol_version": 19,
  "release_notes": "PATCH_NOTES_v0.8.21.md"
}
```

For Desktop v0.8.21 specifically, the verifier requires Unity Tool `0.5.10-TB16`, OSC Protocol `19`, and the Protocol 19 Unity compatibility markers to exist in the Desktop source. This prevents an older Desktop checkout from being relabeled and published as v0.8.21.

## Produced assets

A release build writes assets under `release/<tag>/`:

- `Stories_Of_Yggdrasil_OSC_Windows_<tag>.zip`
- matching `.sha256`
- `SHA256SUMS.txt`
- the current patch notes
- `version.json`

The ZIP contains the PyInstaller application, README/quick-start/changelog, current patch notes, `version.json`, and the OSC contracts/registries.

Sam.py is not built or modified by this repository workflow.
