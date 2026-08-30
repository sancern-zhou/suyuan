param(
    [string]$ApiBaseUrl = "http://219.135.180.51:54333",
    [switch]$Install,
    [string]$DeviceId = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendEnvPath = Join-Path $projectRoot "backend\.env"

if (-not (Test-Path $backendEnvPath)) {
    throw "Backend environment file not found: $backendEnvPath"
}

function Read-DotEnvValue([string]$name) {
    $line = Get-Content $backendEnvPath | Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -First 1
    if (-not $line) { return "" }
    $value = ($line -split "=", 2)[1].Trim()
    if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    return $value.Trim()
}

$pushProvider = Read-DotEnvValue "PUSH_PROVIDER"
$getuiAppId = Read-DotEnvValue "PUSH_GETUI_APP_ID"
if ($pushProvider.ToLowerInvariant() -ne "getui" -or [string]::IsNullOrWhiteSpace($getuiAppId)) {
    throw "PUSH_PROVIDER must be getui and PUSH_GETUI_APP_ID must be configured in $backendEnvPath"
}

$javaHome = [Environment]::GetEnvironmentVariable("JAVA_HOME", "User")
if (-not $javaHome -or -not (Test-Path (Join-Path $javaHome "bin\java.exe"))) {
    $javaHome = "C:\Program Files\Eclipse Adoptium\jdk-17.0.16.8-hotspot"
}
if (-not (Test-Path (Join-Path $javaHome "bin\java.exe"))) {
    throw "JDK 17 not found. Set the user JAVA_HOME or install JDK 17."
}
$env:JAVA_HOME = $javaHome

Write-Host "Building Android Debug APK with JDK 17 and the backend GeTui App ID."
& (Join-Path $PSScriptRoot "gradlew.bat") ":app:assembleDebug" "-PgetuiAppId=$getuiAppId" "-PapiBaseUrl=$ApiBaseUrl"
if ($LASTEXITCODE -ne 0) { throw "Gradle build failed with exit code $LASTEXITCODE" }

$apkPath = Join-Path $PSScriptRoot "app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $apkPath)) { throw "APK was not produced: $apkPath" }
Write-Host "APK: $apkPath"

if ($Install) {
    $adbArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($DeviceId)) { $adbArgs += @("-s", $DeviceId) }
    $adbArgs += @("install", "-r", $apkPath)
    & adb @adbArgs
    if ($LASTEXITCODE -ne 0) { throw "ADB install failed with exit code $LASTEXITCODE" }
}
