$ErrorActionPreference = "Stop"

Write-Host "Suyuan Android build environment"

$savedErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$jdkCandidates = @(
    $env:JAVA_HOME,
    "C:\Program Files\Eclipse Adoptium\jdk-17.0.16.8-hotspot",
    "C:\Users\$env:USERNAME\AppData\Local\Android\android-studio\jbr"
) | Where-Object { $_ -and (Test-Path (Join-Path $_ "bin\java.exe")) } | Select-Object -Unique

$javaHome = $null
$javaVersion = $null
foreach ($candidate in $jdkCandidates) {
    $candidateVersion = (& (Join-Path $candidate "bin\java.exe") -version 2>&1 | Select-Object -First 1).ToString()
    if ($candidateVersion -match '"(?<major>\d+)' -and [int]$Matches.major -ge 17) {
        $javaHome = $candidate
        $javaVersion = $candidateVersion
        break
    }
}
$ErrorActionPreference = $savedErrorAction
if (-not $javaHome) {
    Write-Error "JDK 17 not found. Install JDK 17 and set JAVA_HOME; Java 11 or older is not supported."
}

Write-Host "JDK 17: $javaHome ($javaVersion)"

$sdkCandidates = @(@(
    $env:ANDROID_SDK_ROOT,
    $env:ANDROID_HOME,
    "$env:LOCALAPPDATA\Android\Sdk"
) | Where-Object { $_ -and (Test-Path $_) })

if (-not $sdkCandidates) {
    Write-Error "Android SDK not found. Install SDK 34 and set ANDROID_HOME or ANDROID_SDK_ROOT."
}

$sdk = $sdkCandidates[0]
$platform = Join-Path $sdk "platforms\android-34"
if (-not (Test-Path $platform)) {
    Write-Error "Android SDK 34 platform is missing: $platform"
}

Write-Host "Android SDK: $sdk"
Write-Host "Environment is ready. Run: .\gradlew.bat :app:assembleDebug"
