param(
    [Parameter(Mandatory=$true)]
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path $RepoRoot).Path
Set-Location $RepoRoot

$GitCandidates = @(
    'C:\Program Files\Git\cmd\git.exe',
    'C:\Program Files\Git\bin\git.exe',
    "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
)
$Git = $GitCandidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
if (-not $Git) { throw 'Git was not found. Install Git or update this script with the correct git.exe path.' }

if (-not (Test-Path (Join-Path $RepoRoot '.git'))) {
    throw "Not a Git working tree: $RepoRoot"
}

Write-Host '=== Stories OSC v0.8.20 partial-patch recovery ==='
Write-Host "Repo: $RepoRoot"
Write-Host "Git:  $Git"

$HeadVersionText = & $Git show 'HEAD:version.json' 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Unable to read HEAD:version.json.' }
$HeadVersion = ($HeadVersionText -join "`n") | ConvertFrom-Json
if ([string]$HeadVersion.version -ne '0.8.19') {
    throw "Expected committed HEAD to be v0.8.19. Found: $($HeadVersion.version)"
}

$WorkVersionPath = Join-Path $RepoRoot 'version.json'
if (-not (Test-Path $WorkVersionPath -PathType Leaf)) { throw 'Working version.json is missing.' }
$WorkVersion = Get-Content $WorkVersionPath -Raw | ConvertFrom-Json
if ([string]$WorkVersion.version -ne '0.8.20') {
    throw "Expected partially patched worktree to be v0.8.20. Found: $($WorkVersion.version)"
}

# These files are byte-for-byte unchanged between v0.8.19 and v0.8.20.
# Restore them from committed v0.8.19 HEAD so a partial patch cannot leave holes.
$InheritedFiles = @(
    'stories_yggdrasil_osc/tls_runtime.py',
    'stories_yggdrasil_osc/qol.py',
    'stories_yggdrasil_osc/config.py',
    'contracts/OSC_CONTRACT_v15.json',
    'contracts/OSC_CONTRACT_v16.json',
    'contracts/OSC_CONTRACT_v17.json',
    'contracts/OSC_CONTRACT_v18.json',
    'stories_yggdrasil_osc/combat_authority.py',
    'stories_yggdrasil_osc/app.py',
    'stories_yggdrasil_osc/controller.py',
    'stories_yggdrasil_osc/update_manager.py',
    'requirements.txt',
    'requirements-build.txt',
    'Stories Of Yggdrasil OSC.spec',
    '.github/workflows/release.yml',
    'tests/test_tls_runtime_v0819.py',
    'tests/test_combat_authority_v0818.py',
    'assets/stories_osc_icon.ico',
    'Start Stories OSC.bat'
)

Write-Host "`n=== Restoring unchanged v0.8.19 dependencies ==="
foreach ($relative in $InheritedFiles) {
    & $Git cat-file -e "HEAD:$relative" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Required inherited file is not present in committed v0.8.19 HEAD: $relative"
    }
    & $Git restore --source=HEAD --worktree -- $relative
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restore inherited file: $relative"
    }
    Write-Host "Restored: $relative"
}

$V0820Files = @(
    'main.py',
    'stories_yggdrasil_osc/app_v0814.py',
    'stories_yggdrasil_osc/sam_client.py',
    'stories_yggdrasil_osc/winhttp_transport.py',
    'tests/test_winhttp_transport_v0820.py',
    'audit_source.py',
    'BUILD_AND_PACKAGE_v0.8.20.ps1',
    'PATCH_NOTES_v0.8.20.md',
    'RELEASE_NOTES_0.8.20.txt',
    'version.json'
)

Write-Host "`n=== Verifying v0.8.20 payload files ==="
foreach ($relative in $V0820Files) {
    $path = Join-Path $RepoRoot $relative
    if (-not (Test-Path $path -PathType Leaf)) {
        throw "Missing v0.8.20 payload file: $relative"
    }
    Write-Host "Present:  $relative"
}

$SamText = Get-Content (Join-Path $RepoRoot 'stories_yggdrasil_osc/sam_client.py') -Raw
if ($SamText -notmatch 'winhttp_request' -or $SamText -notmatch 'Windows WinHTTP/Schannel') {
    throw 'sam_client.py does not contain the expected v0.8.20 WinHTTP markers.'
}

Write-Host "`n=== Preparing repository environment ==="
$Launcher = Join-Path $RepoRoot 'Start Stories OSC.bat'
& $Launcher --prepare-only
if ($LASTEXITCODE -ne 0) { throw "Environment preparation failed with exit code $LASTEXITCODE" }

$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python -PathType Leaf)) { throw "Missing repository Python environment after preparation: $Python" }

Write-Host "`n=== Running v0.8.20 source audit ==="
& $Python (Join-Path $RepoRoot 'audit_source.py')
if ($LASTEXITCODE -ne 0) { throw "v0.8.20 source audit failed with exit code $LASTEXITCODE" }

Write-Host "`n=== Building clean v0.8.20 Windows release ==="
& (Join-Path $RepoRoot 'BUILD_AND_PACKAGE_v0.8.20.ps1')
if ($LASTEXITCODE -ne 0) { throw "v0.8.20 build failed with exit code $LASTEXITCODE" }

Write-Host "`n=== Git status ==="
& $Git status --short

$Zip = Join-Path $RepoRoot 'Stories_Of_Yggdrasil_OSC_Windows_v0.8.20.zip'
if (-not (Test-Path $Zip -PathType Leaf)) { throw "Build completed without expected release ZIP: $Zip" }
$Hash = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLowerInvariant()

Write-Host "`nRECOVERY COMPLETE"
Write-Host "Release: $Zip"
Write-Host "SHA-256: $Hash"
Write-Host 'Sam.py was not modified.'
