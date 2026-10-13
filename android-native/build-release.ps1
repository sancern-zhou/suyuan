# 正式出包脚本：构建 release APK 并做签名校验。
# 用法示例：
#   .\build-release.ps1 -VersionCode 2 -VersionName "1.0.1"
#   .\build-release.ps1 -VersionCode 2 -VersionName "1.0.1" -ExpectedCertSha256 ab12... -Install
# 签名治理规则见 RELEASE_SIGNING.md。
param(
    [Parameter(Mandatory = $true)][int]$VersionCode,
    [Parameter(Mandatory = $true)][string]$VersionName,
    [string]$ApiBaseUrl = "http://117.159.53.11:60787/suyuan",
    [string]$GetuiAppId,
    [string]$ExpectedCertSha256,
    [switch]$Install,
    [string]$DeviceId
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
if (-not $ProjectDir) { $ProjectDir = (Get-Location).Path }

# 1. 签名配置必须就位（正式出包的硬前提）。
if (-not (Test-Path (Join-Path $ProjectDir "keystore.properties"))) {
    throw "缺少 android-native/keystore.properties：从 keystore.properties.example 复制并填入正式密钥信息（见 RELEASE_SIGNING.md）。禁止用调试签名出对外包。"
}

# 2. JDK 17 校验（Gradle 依赖 JAVA_HOME）。
if (-not $env:JAVA_HOME -or -not (Test-Path (Join-Path $env:JAVA_HOME "bin\java.exe"))) {
    throw "JAVA_HOME 未设置或无效，请指向 JDK 17（本工程要求 JDK 17 + Android SDK 34）。"
}
$jdkVersion = cmd /c "`"$env:JAVA_HOME\bin\java.exe`" -version 2>&1" | Out-String
if ($jdkVersion -notmatch 'version "17') {
    throw "JAVA_HOME 指向的不是 JDK 17：$jdkVersion"
}

# 3. 读取 Android SDK 位置（local.properties）。
$sdkDir = $null
Get-Content (Join-Path $ProjectDir "local.properties") | ForEach-Object {
    if ($_ -match '^\s*sdk\.dir\s*=\s*(.+)$') { $sdkDir = $Matches[1].Trim() }
}
if (-not $sdkDir -or -not (Test-Path $sdkDir)) { throw "无法从 local.properties 解析 Android SDK 路径。" }

# 4. 个推 App ID：优先用参数，否则从 backend/.env 读取。
if (-not $GetuiAppId) {
    $envFile = Join-Path (Split-Path $ProjectDir -Parent) "backend\.env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*PUSH_GETUI_APP_ID\s*=\s*(.+)$') { $GetuiAppId = $Matches[1].Trim() }
        }
    }
}
if (-not $GetuiAppId) { Write-Warning "未提供 getuiAppId（参数或 backend/.env 的 PUSH_GETUI_APP_ID），本包将不带推送能力。" }

# 5. 构建 release APK。
$gradleArgs = @("assembleRelease", "-PversionCode=$VersionCode", "-PversionName=$VersionName", "-PapiBaseUrl=$ApiBaseUrl")
if ($GetuiAppId) { $gradleArgs += "-PgetuiAppId=$GetuiAppId" }
Push-Location $ProjectDir
try {
    & .\gradlew.bat @gradleArgs
    if ($LASTEXITCODE -ne 0) { throw "gradlew assembleRelease 失败（exit $LASTEXITCODE）。" }
}
finally { Pop-Location }

$apk = Join-Path $ProjectDir "app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path $apk)) { throw "未找到构建产物：$apk" }

# 6. 签名校验：apksigner 验证完整性，并输出证书 SHA-256 指纹。
$buildToolsDir = Get-ChildItem (Join-Path $sdkDir "build-tools") -Directory |
    Sort-Object { [version]($_.Name -replace '[^0-9.]', '') } -Descending |
    Select-Object -First 1
$apksigner = Join-Path $buildToolsDir.FullName "apksigner.bat"
& $apksigner verify $apk
if ($LASTEXITCODE -ne 0) { throw "apksigner verify 失败：APK 签名无效。" }
$certsOutput = & $apksigner verify --print-certs $apk | Out-String
$certSha256 = $null
if ($certsOutput -match 'SHA-256 digest:\s*([0-9a-fA-F:]+)') {
    $certSha256 = ($Matches[1] -replace ':', '').ToLowerInvariant()
}

# 7. 与登记指纹比对（可选，强烈建议在发版 checklist 中传入）。
if ($ExpectedCertSha256) {
    $expected = ($ExpectedCertSha256 -replace ':', '').ToLowerInvariant()
    if ($certSha256 -ne $expected) {
        throw "签名指纹不匹配！期望 $expected，实际 $certSha256。拒绝分发，请核对 keystore 是否为登记的正式密钥。"
    }
    Write-Host "签名指纹与登记一致：$certSha256" -ForegroundColor Green
}

# 8. 可选直接安装到设备。
if ($Install) {
    $adb = Join-Path $sdkDir "platform-tools\adb.exe"
    $installArgs = @("install", "-r")
    if ($DeviceId) { $installArgs = @("-s", $DeviceId) + $installArgs }
    & $adb @installArgs $apk
    if ($LASTEXITCODE -ne 0) { throw "adb install 失败（exit $LASTEXITCODE）。" }
}

Write-Host ""
Write-Host "==== 出包结果 ====" -ForegroundColor Cyan
Write-Host "APK        : $apk"
Write-Host "versionCode: $VersionCode  versionName: $VersionName"
Write-Host "ApiBaseUrl : $ApiBaseUrl"
if ($certSha256) { Write-Host "证书SHA-256: $certSha256" }
if (-not $ExpectedCertSha256) {
    Write-Host "提醒：请将上面指纹与 RELEASE_SIGNING.md 登记值比对后再分发。" -ForegroundColor Yellow
}
