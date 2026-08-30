pluginManagement {
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://mvn.getui.com/nexus/content/repositories/releases/") }
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://mvn.getui.com/nexus/content/repositories/releases/") }
    }
    versionCatalogs {
        create("libs") {
            version("agp", "8.6.0")
            version("kotlin", "1.9.24")
            version("composeBom", "2024.06.00")
            version("activity", "1.9.2")
            version("core", "1.13.1")
            version("lifecycle", "2.8.6")
            version("okhttp", "4.12.0")
            version("coroutines", "1.8.1")
            version("getui", "3.3.15.0")
            version("getuiGtc", "3.3.3.0")
            plugin("androidApplication", "com.android.application").versionRef("agp")
            plugin("kotlinAndroid", "org.jetbrains.kotlin.android").versionRef("kotlin")
            library("androidx-activity-compose", "androidx.activity", "activity-compose").versionRef("activity")
            library("androidx-core-ktx", "androidx.core", "core-ktx").versionRef("core")
            library("androidx-lifecycle-runtime-compose", "androidx.lifecycle", "lifecycle-runtime-compose").versionRef("lifecycle")
            library("androidx-lifecycle-viewmodel-compose", "androidx.lifecycle", "lifecycle-viewmodel-compose").versionRef("lifecycle")
            library("androidx-compose-bom", "androidx.compose", "compose-bom").versionRef("composeBom")
            library("androidx-compose-ui", "androidx.compose.ui", "ui").withoutVersion()
            library("androidx-compose-ui-tooling", "androidx.compose.ui", "ui-tooling").withoutVersion()
            library("androidx-compose-material3", "androidx.compose.material3", "material3").withoutVersion()
            library("okhttp", "com.squareup.okhttp3", "okhttp").versionRef("okhttp")
            library("kotlinx-coroutines-android", "org.jetbrains.kotlinx", "kotlinx-coroutines-android").versionRef("coroutines")
            library("getui-sdk", "com.getui", "gtsdk").versionRef("getui")
            library("getui-gtc", "com.getui", "gtc").versionRef("getuiGtc")
        }
    }
}

rootProject.name = "SuyuanAndroid"
include(":app")
