param(
    [string]$DataDirectory = "./data",
    [string]$BackupDirectory = "./backups"
)

$source = Join-Path $DataDirectory "itdesk.db"
if (-not (Test-Path -LiteralPath $source)) {
    throw "Database not found: $source"
}

New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destination = Join-Path $BackupDirectory "itdesk-$stamp.db"
Copy-Item -LiteralPath $source -Destination $destination -Force
Write-Output "Backup created: $destination"
