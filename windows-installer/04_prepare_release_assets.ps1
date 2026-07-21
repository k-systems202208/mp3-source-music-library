param(
    [string]$Version = '2.6.1'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $root "release\MusicLibrary-Setup-$Version-x64.exe"
$userReadme = Join-Path $root 'docs\README_USER.txt'
$notesSource = Join-Path $root "RELEASE_NOTES_v$Version.md"
$output = Join-Path $root "release-assets\v$Version"

if (-not (Test-Path $installer)) {
    Write-Host ''
    Write-Host 'Installer was not found:'
    Write-Host $installer
    Write-Host ''
    Write-Host 'Run 00_build_installer.bat first.'
    exit 1
}

if (Test-Path $output) {
    Remove-Item $output -Recurse -Force
}
New-Item -ItemType Directory -Path $output -Force | Out-Null

$copiedInstaller = Join-Path $output (Split-Path $installer -Leaf)
Copy-Item $installer $copiedInstaller -Force

if (Test-Path $userReadme) {
    Copy-Item $userReadme (Join-Path $output 'README_USER.txt') -Force
}

if (Test-Path $notesSource) {
    Copy-Item $notesSource (Join-Path $output "RELEASE_NOTES_v$Version.md") -Force
}

$hash = Get-FileHash -Algorithm SHA256 -Path $copiedInstaller
$hashLine = "$($hash.Hash.ToLower())  $($hash.Path | Split-Path -Leaf)"
$hashLine | Set-Content (Join-Path $output 'SHA256SUMS.txt') -Encoding ascii

Write-Host ''
Write-Host 'GitHub Release assets were prepared:'
Write-Host $output
Write-Host ''
Write-Host $hashLine
Write-Host ''

Start-Process explorer.exe -ArgumentList "`"$output`""
