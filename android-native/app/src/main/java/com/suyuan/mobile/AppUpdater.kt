package com.suyuan.mobile

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.security.MessageDigest

sealed class UpdateState {
    data object Idle : UpdateState()
    data class Available(val info: AppUpdateInfo, val forced: Boolean) : UpdateState()
    data class Downloading(val info: AppUpdateInfo, val forced: Boolean, val progress: Int) : UpdateState()
    data class ReadyToInstall(val info: AppUpdateInfo, val forced: Boolean, val apk: File) : UpdateState()
    data class Failed(val info: AppUpdateInfo, val forced: Boolean, val message: String) : UpdateState()
}

class AppUpdater(
    private val context: Context,
    private val api: SocialAppApi,
) {
    // 自持作用域：下载不随 ViewModel 重建中断，随进程存活。
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val _state = MutableStateFlow<UpdateState>(UpdateState.Idle)
    val state: StateFlow<UpdateState> = _state.asStateFlow()
    private var skippedVersionCode: Int? = null

    suspend fun checkOnLaunch() {
        val current = _state.value
        if (current !is UpdateState.Idle) return
        val info = api.checkLatestVersion() ?: return
        if (info.versionCode <= BuildConfig.VERSION_CODE &&
            info.minVersionCode <= BuildConfig.VERSION_CODE
        ) return
        if (skippedVersionCode == info.versionCode && BuildConfig.VERSION_CODE >= info.minVersionCode) return
        _state.value = UpdateState.Available(info, BuildConfig.VERSION_CODE < info.minVersionCode)
    }

    fun dismiss(info: AppUpdateInfo) {
        skippedVersionCode = info.versionCode
        _state.value = UpdateState.Idle
    }

    fun download(info: AppUpdateInfo, forced: Boolean) {
        if (_state.value is UpdateState.Downloading) return
        _state.value = UpdateState.Downloading(info, forced, 0)
        scope.launch {
            val dest = File(context.cacheDir, "apk_updates/${info.versionName}-${info.versionCode}.apk")
            try {
                withContext(Dispatchers.IO) {
                    dest.parentFile?.mkdirs()
                    dest.delete()
                }
                val ok = api.downloadApk(info.downloadUrl, dest) { progress ->
                    _state.value = UpdateState.Downloading(info, forced, progress)
                }
                if (!ok) {
                    _state.value = UpdateState.Failed(info, forced, "下载失败，请稍后重试")
                    return@launch
                }
                val expected = info.sha256
                if (expected != null && !sha256Of(dest).equals(expected, ignoreCase = true)) {
                    dest.delete()
                    _state.value = UpdateState.Failed(info, forced, "安装包校验失败，已放弃安装")
                    return@launch
                }
                _state.value = UpdateState.ReadyToInstall(info, forced, dest)
            } catch (e: Exception) {
                _state.value = UpdateState.Failed(info, forced, e.message ?: "下载异常")
            }
        }
    }

    fun canInstallNow(): Boolean = context.packageManager.canRequestPackageInstalls()

    fun unknownSourcesSettingsIntent(): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    fun installIntent(apk: File): Intent {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", apk)
        return Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    }
}

private fun sha256Of(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input ->
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val read = input.read(buffer)
            if (read <= 0) break
            digest.update(buffer, 0, read)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}
