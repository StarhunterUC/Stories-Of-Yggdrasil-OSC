# GitHub update notes

Repository:

```text
StarhunterUC/Stories-Of-Yggdrasil-OSC
```

For v0.8.7:

```powershell
git status
git add .
git commit -m "Stories Of Yggdrasil OSC v0.8.7"
git push origin main

git tag -a v0.8.7 -m "Stories Of Yggdrasil OSC v0.8.7"
git push origin v0.8.7
```

The release workflow runs the test suite, builds the Windows executable, and publishes the ZIP plus SHA-256 file.
