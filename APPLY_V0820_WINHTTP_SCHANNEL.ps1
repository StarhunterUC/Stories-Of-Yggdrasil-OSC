param(
    [Parameter(Mandatory=$true)]
    [string]$RepoRoot,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $RepoRoot).Path
$Payload = Join-Path $PSScriptRoot "payload"
$VersionFile = Join-Path $RepoRoot "version.json"

if (-not (Test-Path $VersionFile -PathType Leaf)) {
    throw "Not a Stories Of Yggdrasil OSC repository: version.json was not found in $RepoRoot"
}

$metadata = Get-Content $VersionFile -Raw | ConvertFrom-Json
if ([string]$metadata.version -ne "0.8.19") {
    throw "v0.8.20 patch requires Desktop v0.8.19 baseline. Found: $($metadata.version)"
}

$samClient = Join-Path $RepoRoot "stories_yggdrasil_osc\sam_client.py"
if (-not (Test-Path $samClient -PathType Leaf)) {
    throw "Missing current Sam client: $samClient"
}
$currentSamClient = Get-Content $samClient -Raw
if ($currentSamClient -notmatch "get_ssl_context") {
    throw "The Sam client does not look like the v0.8.19 baseline. Refusing to overwrite it."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path $RepoRoot "backups\v0820-winhttp-schannel-$stamp"
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

Write-Host "Backing up v0.8.19 files to: $BackupRoot"

Get-ChildItem $Payload -File -Recurse | ForEach-Object {
    $relative = $_.FullName.Substring($Payload.Length).TrimStart('\')
    $destination = Join-Path $RepoRoot $relative
    if (Test-Path $destination -PathType Leaf) {
        $backup = Join-Path $BackupRoot $relative
        $backupParent = Split-Path -Parent $backup
        New-Item -ItemType Directory -Force -Path $backupParent | Out-Null
        Copy-Item $destination $backup -Force
    }
}

Write-Host "Installing Desktop v0.8.20 WinHTTP/Schannel transport..."
Get-ChildItem $Payload -File -Recurse | ForEach-Object {
    $relative = $_.FullName.Substring($Payload.Length).TrimStart('\')
    $destination = Join-Path $RepoRoot $relative
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item $_.FullName $destination -Force
}

# A new executable must never be paired with an older PyInstaller runtime.
Remove-Item (Join-Path $RepoRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $RepoRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $RepoRoot "release") -Recurse -Force -ErrorAction SilentlyContinue

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $Python -PathType Leaf) {
    Push-Location $RepoRoot
    try {
        & $Python audit_source.py
        if ($LASTEXITCODE -ne 0) { throw "v0.8.20 source audit failed." }
    }
    finally { Pop-Location }
}
else {
    $Py = Get-Command py -ErrorAction SilentlyContinue
    if ($Py) {
        Push-Location $RepoRoot
        try {
            & py audit_source.py
            if ($LASTEXITCODE -ne 0) { throw "v0.8.20 source audit failed." }
        }
        finally { Pop-Location }
    }
    else {
        Write-Warning "Python is not currently available, so the source audit was not run. The build script will prepare the repo environment."
    }
}

if ($Build) {
    Write-Host "Building clean Windows v0.8.20 release..."
    & (Join-Path $RepoRoot "BUILD_AND_PACKAGE_v0.8.20.ps1")
    if ($LASTEXITCODE -ne 0) { throw "v0.8.20 build failed with exit code $LASTEXITCODE" }
}

Write-Host ""
Write-Host "Stories Of Yggdrasil OSC Desktop v0.8.20 installed."
Write-Host "Sam.py was not modified."
Write-Host "Windows Sam.py HTTPS transport: WinHTTP + Schannel"
Write-Host "Backup: $BackupRoot"
