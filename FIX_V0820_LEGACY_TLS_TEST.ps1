param(
    [Parameter(Mandatory=$true)]
    [string]$RepoRoot,
    [switch]$Build
)

$ErrorActionPreference = 'Stop'
Set-Location $RepoRoot

$testFile = Join-Path $RepoRoot 'tests\test_tls_runtime_v0819.py'
if (-not (Test-Path $testFile)) {
    throw "Missing test file: $testFile"
}

$versionFile = Join-Path $RepoRoot 'version.json'
if (-not (Test-Path $versionFile)) {
    throw "Missing version.json"
}
$version = (Get-Content $versionFile -Raw | ConvertFrom-Json).version
if ($version -ne '0.8.20') {
    throw "Expected v0.8.20 working tree, found $version"
}

$text = Get-Content $testFile -Raw
$needle = '        with patch("stories_yggdrasil_osc.sam_client.get_ssl_context", return_value=fake_context), \'
$replacement = @'
        with patch("stories_yggdrasil_osc.sam_client.winhttp_available", return_value=False), \
             patch("stories_yggdrasil_osc.sam_client.get_ssl_context", return_value=fake_context), \
'@

if ($text -match 'sam_client\.winhttp_available", return_value=False') {
    Write-Host 'Legacy TLS fallback test is already patched.'
} elseif ($text.Contains($needle)) {
    $text = $text.Replace($needle + "`r`n", $replacement.Replace("`n", "`r`n"))
    if ($text -eq (Get-Content $testFile -Raw)) {
        # Retry LF-only files.
        $text = (Get-Content $testFile -Raw).Replace($needle + "`n", $replacement)
    }
    Set-Content -Path $testFile -Value $text -Encoding UTF8
    Write-Host 'Patched v0.8.19 urllib test to force the v0.8.20 Python fallback transport.'
} else {
    throw 'Expected v0.8.19 test block was not found; refusing to modify the file automatically.'
}

$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "Missing venv Python: $python"
}

Write-Host "`n=== SOURCE AUDIT ==="
& $python '.\audit_source.py'
if ($LASTEXITCODE -ne 0) { throw 'v0.8.20 source audit failed.' }

Write-Host "`n=== TEST SUITE ==="
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'v0.8.20 tests failed.' }

if ($Build) {
    Write-Host "`n=== BUILD ==="
    & '.\BUILD_AND_PACKAGE_v0.8.20.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'v0.8.20 build failed.' }
}
