import java.util.Properties
import org.gradle.api.Action
import org.gradle.api.execution.TaskExecutionGraph

plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.kotlinAndroid)
}

// Formal signing is loaded from the git-ignored keystore.properties at the project root.
// When present, every build type signs with the formal key so any machine's APK can
// cover-install over an installed one; without it only debug compiles, release is blocked.
val signingProps = Properties()
val signingPropsFile = rootProject.file("keystore.properties")
if (signingPropsFile.exists()) {
    signingPropsFile.inputStream().use { signingProps.load(it) }
}
val releaseStoreFilePath = signingProps.getProperty("storeFile")?.trim()?.takeIf { it.isNotEmpty() }
val hasReleaseSigning = releaseStoreFilePath != null &&
    !signingProps.getProperty("storePassword").isNullOrBlank() &&
    !signingProps.getProperty("keyAlias").isNullOrBlank() &&
    !signingProps.getProperty("keyPassword").isNullOrBlank()

android {
    namespace = "com.suyuan.mobile"
    compileSdk = 34

    val versionCodeProp = (project.findProperty("versionCode") as String?)?.trim()?.takeIf { it.isNotEmpty() }
    val versionNameProp = (project.findProperty("versionName") as String?)?.trim()?.takeIf { it.isNotEmpty() }

    defaultConfig {
        applicationId = "com.suyuan.mobile"
        minSdk = 26
        targetSdk = 34
        versionCode = versionCodeProp?.toIntOrNull()
            ?: (versionCodeProp?.let { throw GradleException("versionCode 必须是整数，收到 \"$versionCodeProp\"") } ?: 1)
        versionName = versionNameProp ?: "0.1.0"
        manifestPlaceholders["GETUI_APPID"] = (project.findProperty("getuiAppId") as String?)?.trim().orEmpty()
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = rootProject.file(releaseStoreFilePath!!)
                storePassword = signingProps.getProperty("storePassword")
                keyAlias = signingProps.getProperty("keyAlias")
                keyPassword = signingProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            } else {
                logger.warn("AGP: 未找到 android-native/keystore.properties，debug 包回退为调试签名，无法覆盖安装正式包（见 RELEASE_SIGNING.md）")
            }
        }
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
    val configuredApiBaseUrl = (project.findProperty("apiBaseUrl") as String?)
        ?.trim()
        ?.takeIf { it.isNotEmpty() }
        ?: "http://117.159.53.11:60787/suyuan"
    val escapedApiBaseUrl = configuredApiBaseUrl
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
    buildTypes.all {
        buildConfigField("String", "API_BASE_URL", "\"$escapedApiBaseUrl\"")
        val getuiAppId = (project.findProperty("getuiAppId") as String?)?.trim().orEmpty()
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
        buildConfigField("String", "GETUI_APPID", "\"$getuiAppId\"")
    }
}

// Fail fast on release builds without formal signing, while keeping debug/test builds
// runnable on machines that only hold compile dependencies (AGP configures all build
// types up front, so the check must happen when the task graph is known).
gradle.taskGraph.whenReady(object : Action<TaskExecutionGraph> {
    override fun execute(graph: TaskExecutionGraph) {
        if (!hasReleaseSigning && graph.allTasks.any { it.name.contains("Release") }) {
            throw GradleException(
                "Release 构建缺少正式签名：请在 android-native/keystore.properties 配置密钥" +
                    "（模板见 keystore.properties.example，流程见 RELEASE_SIGNING.md）。" +
                    "禁止用调试签名出对外包。"
            )
        }
    }
})

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.json:json:20240303")
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.material3)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.getui.sdk)
    implementation(libs.getui.gtc)
    debugImplementation(libs.androidx.compose.ui.tooling)
}

// Consume the shared frontend build, retaining only the chart entry's dependencies.
val chartAssets = layout.buildDirectory.dir("generated/chartAssets")
val packageChartRenderer by tasks.registering(Exec::class) {
    val frontend = rootProject.projectDir.parentFile.resolve("frontend")
    inputs.dir(frontend.resolve("dist"))
    inputs.file(frontend.resolve("scripts/packageChartRenderer.mjs"))
    outputs.dir(chartAssets)
    commandLine("node", frontend.resolve("scripts/packageChartRenderer.mjs").absolutePath,
        frontend.resolve("dist").absolutePath, chartAssets.get().asFile.resolve("charts").absolutePath)
}
android.sourceSets.getByName("main").assets.srcDir(chartAssets)
tasks.named("preBuild").configure { dependsOn(packageChartRenderer) }
