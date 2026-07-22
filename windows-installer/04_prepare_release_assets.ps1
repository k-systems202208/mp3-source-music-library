param(
    [string]$Version = '2.6.2'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$installerName = "MusicLibrary-Setup-$Version-x64.exe"
$installer = Join-Path $root "release\$installerName"
$output = Join-Path $root "release-assets\v$Version"

$files = @(
    @{
        Source = $installer
        Destination = $installerName
        Required = $true
    },
    @{
        Source = (Join-Path $root 'docs\README_USER.txt')
        Destination = 'README_USER.txt'
        Required = $true
    },
    @{
        Source = (Join-Path $root 'docs\REMOTE_ACCESS_USER.txt')
        Destination = 'REMOTE_ACCESS_USER.txt'
        Required = $true
    },
    @{
        Source = (Join-Path $root 'docs\REMOTE_ACCESS_FAMILY.txt')
        Destination = 'REMOTE_ACCESS_FAMILY.txt'
        Required = $true
    },
    @{
        Source = (Join-Path $root "RELEASE_NOTES_v$Version.md")
        Destination = "RELEASE_NOTES_v$Version.md"
        Required = $true
    }
)

foreach ($file in $files) {
    if ($file.Required -and -not (Test-Path $file.Source)) {
        Write-Host ''
        Write-Host 'Required file was not found:'
        Write-Host $file.Source
        Write-Host ''
        if ($file.Source -eq $installer) {
            Write-Host 'Run 00_build_installer.bat first.'
        }
        exit 1
    }
}

if (Test-Path $output) {
    Remove-Item $output -Recurse -Force
}
New-Item -ItemType Directory -Path $output -Force | Out-Null

foreach ($file in $files) {
    Copy-Item `
        -Path $file.Source `
        -Destination (Join-Path $output $file.Destination) `
        -Force
}

$copiedInstaller = Join-Path $output $installerName
$hash = Get-FileHash -Algorithm SHA256 -Path $copiedInstaller
$hashLine = "$($hash.Hash.ToLower())  $installerName"
$hashLine | Set-Content `
    (Join-Path $output 'SHA256SUMS.txt') `
    -Encoding ascii

Write-Host ''
Write-Host 'GitHub Release assets were prepared:'
Write-Host $output
Write-Host ''
Get-ChildItem $output | ForEach-Object {
    Write-Host "  $($_.Name)"
}
Write-Host ''
Write-Host $hashLine
Write-Host ''

Start-Process explorer.exe -ArgumentList "`"$output`""
