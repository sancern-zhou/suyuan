package com.suyuan.mobile

import android.annotation.SuppressLint
import android.graphics.Color
import android.net.Uri
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

/**
 * 受限远程页面白名单：大屏直连是有意放宽的既定「禁止远程导航」策略——
 * 仅允许编译期配置的 Web 前端域名（同 host 全部放行，页面需要加载
 * JS/CSS 并向同域网关发 API 请求）；任何跨域跳转/子资源一律拒绝。
 * 令牌只拼进首屏 URL，页面内部导航不注入。
 */
internal fun isAllowedDashboardHost(allowedBaseUrl: String, target: String): Boolean {
    val allowedHost = runCatching { Uri.parse(allowedBaseUrl).host?.lowercase() }.getOrNull()
    if (allowedHost.isNullOrEmpty()) return false
    val targetHost = runCatching { Uri.parse(target).host?.lowercase() }.getOrNull()
    return targetHost == allowedHost
}

internal fun dashboardEntryUrl(webBaseUrl: String, path: String, accessToken: String): String? {
    if (!isAllowedDashboardHost(webBaseUrl, webBaseUrl)) return null
    val base = webBaseUrl.trimEnd('/')
    if (!path.startsWith("/") || path.contains("..")) return null
    if (accessToken.isBlank()) return "$base$path"
    return "$base$path?access_token=${android.net.Uri.encode(accessToken)}"
}

private fun buildDashboardWebViewClient(allowedBaseUrl: String): WebViewClient {
    return object : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            // 仅拦截会改变页面的导航；跨域一律拒绝，同域放行。
            return !isAllowedDashboardHost(allowedBaseUrl, request.url.toString())
        }
    }
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
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    settings.allowFileAccess = false
                    settings.allowContentAccess = false
                    settings.javaScriptCanOpenWindowsAutomatically = false
                    setBackgroundColor(Color.WHITE)
                    webViewClient = client
                    loadUrl(entryUrl)
                }
            },
            onRelease = { it.destroy() },
            modifier = Modifier.fillMaxSize()
        )
    }
}
