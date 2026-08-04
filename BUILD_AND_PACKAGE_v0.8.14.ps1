$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Preparing Stories Of Yggdrasil OSC Desktop v0.8.14..."
& ".\Start Stories OSC.bat" --prepare-only
if ($LASTEXITCODE -ne 0) { throw "Environment preparation failed with exit code $LASTEXITCODE" }

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Missing repository Python environment: $Python" }

& $Python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed" }

& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Automated tests failed" }

& $Python audit_source.py
if ($LASTEXITCODE -ne 0) { throw "Source audit failed" }

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $Python -m PyInstaller --noconfirm --clean "Stories Of Yggdrasil OSC.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$ReleaseBase = Join-Path $Root "release"
$ReleaseRoot = Join-Path $ReleaseBase "Stories Of Yggdrasil OSC"
Remove-Item -Recurse -Force $ReleaseBase -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Copy-Item "dist\Stories Of Yggdrasil OSC\*" $ReleaseRoot -Recurse -Force
Copy-Item README.md, QUICK_START.md, CHANGELOG.md, PATCH_NOTES_v0.8.14.md, version.json $ReleaseRoot -Force
Copy-Item contracts (Join-Path $ReleaseRoot "contracts") -Recurse -Force

$Zip = Join-Path $Root "Stories_Of_Yggdrasil_OSC_Windows_v0.8.14.zip"
Remove-Item -Force $Zip, "$Zip.sha256" -ErrorAction SilentlyContinue
Compress-Archive -Path $ReleaseRoot -DestinationPath $Zip -Force
$Hash = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$Hash  $([IO.Path]::GetFileName($Zip))" | Set-Content "$Zip.sha256" -Encoding ascii

Write-Host "Build complete: $Zip"
Write-Host "SHA-256: $Hash"
