# Scripts: scripts/release.ps1
param(
    [string]$Version
)

if (-not $Version) {
    Write-Host "❌ Version parameter is required. Example: .\scripts\release.ps1 -Version 0.2.0" -ForegroundColor Red
    exit 1
}

# Update the VERSION file
$Version | Out-File -FilePath "VERSION" -Encoding utf8

# Git commands
git add .
git commit -m "feat: release v$Version"
git tag "v$Version"

$currentBranch = git branch --show-current
Write-Host "✅ Version v$Version committed and tagged. Now push with:" -ForegroundColor Green
Write-Host "git push origin $currentBranch --tags" -ForegroundColor Yellow