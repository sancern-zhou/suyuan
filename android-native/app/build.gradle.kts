plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.kotlinAndroid)
}

android {
    namespace = "com.suyuan.mobile"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.suyuan.mobile"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        manifestPlaceholders["GETUI_APPID"] = (project.findProperty("getuiAppId") as String?)?.trim().orEmpty()
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
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

dependencies {
    testImplementation("junit:junit:4.13.2")
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
