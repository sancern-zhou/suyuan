package com.suyuan.mobile

import android.annotation.SuppressLint
import android.graphics.Color
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import java.net.URI
import java.net.URLEncoder

/**
 * 受限远程页面白名单：大屏直连是有意放宽的既定「禁止远程导航」策略——
 * 仅允许编译期配置的 Web 前端域名（同 host 全部放行，页面需要加载
 * JS/CSS 并向同域网关发 API 请求）；跨域导航一律拒绝。
 * 令牌只拼进首屏 URL，页面内部导航不注入。
 *
 * 两个入口纯函数用 java.net.URI（JVM 标准库）而不是 android.net.Uri：
 * 本地单元测试的 mockable android.jar 不提供 Uri 实现，用框架类会让
 * DashboardAccessTest 整体失效。
 */
internal fun isAllowedDashboardHost(allowedBaseUrl: String, target: String): Boolean {
    val allowedHost = runCatching { URI(allowedBaseUrl).host?.lowercase() }.getOrNull()
    if (allowedHost.isNullOrEmpty()) return false
    val targetHost = runCatching { URI(target).host?.lowercase() }.getOrNull()
    return targetHost == allowedHost
}

internal fun dashboardEntryUrl(webBaseUrl: String, path: String, accessToken: String): String? {
    if (!isAllowedDashboardHost(webBaseUrl, webBaseUrl)) return null
    val base = webBaseUrl.trimEnd('/')
    // 以 "/" 开头但以 "//" 开头是协议相对地址，无法保证落在本域，一并拒绝
    if (!path.startsWith("/") || path.startsWith("//") || path.contains("..")) return null
    if (accessToken.isBlank()) return "$base$path"
    return "$base$path?access_token=${URLEncoder.encode(accessToken, "UTF-8")}"
}

private fun buildDashboardWebViewClient(allowedBaseUrl: String): WebViewClient {
    return object : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            // 仅拦截会改变页面的导航；跨域一律拒绝，同域放行。
            return !isAllowedDashboardHost(allowedBaseUrl, request.url.toString())
        }
    }
}

private object DashboardWebChromeClient : WebChromeClient() {
    override fun onConsoleMessage(consoleMessage: ConsoleMessage): Boolean {
        // 前端异常原来只在 WebView 内部静默发生，App 侧无法定位；输出到
        // logcat 的 SuyuanDashboard 标签，不记录 URL（首屏 URL 含访问令牌）。
        val message = consoleMessage.message()
        val source = consoleMessage.sourceId()?.substringAfterLast('/') ?: "unknown"
        val line = consoleMessage.lineNumber()
        val text = "[$source:$line] $message"
        when (consoleMessage.messageLevel()) {
            ConsoleMessage.MessageLevel.ERROR -> Log.e(TAG, text)
            ConsoleMessage.MessageLevel.WARNING -> Log.w(TAG, text)
            else -> Log.i(TAG, text)
        }
        return true
    }

    private const val TAG = "SuyuanDashboard"
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
internal fun DashboardWebViewScreen(entryUrl: String?, allowedBaseUrl: String) {
    // 顶栏（AppTopBar）处理状态栏、底部导航栏（BottomNavBar）处理手势条 inset，
    // WebView 填满两者之间的可用区域即可。
    Column(
        Modifier
            .fillMaxSize()
            .background(SuyuanColors.background)
    ) {
        if (entryUrl == null) {
            Column(Modifier.fillMaxSize().systemBarsPadding()) {
                Text(
                    "大屏直连未配置：请通知管理员在 App 发布配置中设置 Web 前端地址与部署令牌。",
                    color = SuyuanColors.secondaryText,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(16.dp)
                )
            }
            return
        }
        val client = remember(allowedBaseUrl) { buildDashboardWebViewClient(allowedBaseUrl) }
        AndroidView(
            factory = { context ->
                WebView(context).apply {
                    // WebView 按自身 LayoutParams 判断高度是否固定；Compose 托管的 View 默认是
                    // 包裹内容，WebView 会把页面布局视口的高度当作 0，100vh / height:100% 全部
                    // 解析为 0，页面内容被外壳的 overflow:hidden 裁成空白。
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT,
                    )
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    settings.allowFileAccess = false
                    settings.allowContentAccess = false
                    settings.javaScriptCanOpenWindowsAutomatically = false
                    setBackgroundColor(Color.WHITE)
                    webViewClient = client
                    webChromeClient = DashboardWebChromeClient
                    loadUrl(entryUrl)
                }
            },
            onRelease = { it.destroy() },
            modifier = Modifier.fillMaxSize()
        )
    }
}
