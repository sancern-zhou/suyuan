package com.suyuan.mobile

import android.content.Context
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import org.json.JSONObject
import java.io.ByteArrayInputStream

internal sealed class ReplyBlock {
    data class Text(val content: String) : ReplyBlock()
    data class Chart(val attachment: UploadedAttachment) : ReplyBlock()
    data class Image(val attachment: UploadedAttachment) : ReplyBlock()
}

private val chartMarker = Regex("\\[\\[chart:([0-9a-f]{32})\\]\\]")
private val backtickRuns = Regex("`+")
private val codeFence = Regex("^ {0,3}(`{3,}|~{3,})(.*)$")
private val quotePrefix = Regex("^ {0,3}>[ \\t]?")

private fun String.isMarkdownEscaped(index: Int): Boolean {
    var start = index
    while (start > 0 && this[start - 1] == '\\') start--
    return (index - start) % 2 == 1
}

private fun chartMarkers(content: String): Sequence<MatchResult> = sequence {
    // Collect ordinary Markdown ranges separately from fenced and indented code.
    var fence: String? = null
    var fenceQuoteDepth = 0
    var start = 0
    var offset = 0
    val textRanges = mutableListOf<IntRange>()
    for (line in content.lineSequence()) {
        var markdown = line
        var quoteDepth = 0
        while (true) {
            val quote = quotePrefix.find(markdown) ?: break
            markdown = markdown.substring(quote.value.length)
            quoteDepth++
        }
        if (fence != null && quoteDepth < fenceQuoteDepth) fence = null
        val candidate = codeFence.find(markdown)
        val delimiter = candidate?.groupValues?.get(1).orEmpty()
        val suffix = candidate?.groupValues?.get(2).orEmpty()
        val next = offset + line.length + when {
            content.startsWith("\r\n", offset + line.length) -> 2
            offset + line.length < content.length -> 1
            else -> 0
        }
        val open = fence
        if (open != null) {
            if (delimiter.startsWith(open) && suffix.isBlank()) fence = null
            start = next
        } else if (delimiter.isNotEmpty() && (delimiter[0] == '~' || '`' !in suffix)) {
            textRanges += start until offset
            fence = delimiter
            fenceQuoteDepth = quoteDepth
            start = next
        } else if (markdown.startsWith("    ") || markdown.startsWith("\t")) {
            textRanges += start until offset
            start = next
        }
        offset = next
    }
    textRanges += start until content.length

    for (range in textRanges) {
        if (range.isEmpty()) continue
        val ticks = backtickRuns.findAll(content, range.first).takeWhile { it.range.last <= range.last }.toList()
        var skipUntil = range.first
        var tickIndex = 0
        for (match in chartMarker.findAll(content, range.first).takeWhile { it.range.last <= range.last }) {
            while (tickIndex < ticks.size && ticks[tickIndex].range.first < match.range.first) {
                val opening = ticks[tickIndex++]
                if (opening.range.first < skipUntil || content.isMarkdownEscaped(opening.range.first)) continue
                val closing = (tickIndex until ticks.size).firstOrNull { ticks[it].value.length == opening.value.length }
                if (closing != null) {
                    skipUntil = ticks[closing].range.last + 1
                    tickIndex = closing + 1
                }
            }
            if (match.range.first >= skipUntil && !content.isMarkdownEscaped(match.range.first)) yield(match)
        }
    }
}

internal fun chartReplyBlocks(content: String, attachments: List<UploadedAttachment>): List<ReplyBlock> {
    val charts = attachments.filter { it.resourceId.isNotBlank() && (isInteractiveChart(it) || isImageAttachment(it)) }
        .associateBy { it.resourceId }
    val blocks = mutableListOf<ReplyBlock>()
    var start = 0
    chartMarkers(content).forEach { match ->
        if (match.range.first > start) blocks += ReplyBlock.Text(content.substring(start, match.range.first))
        val chart = charts[match.groupValues[1]]
        blocks += when {
            chart == null -> ReplyBlock.Text("【图表不可用】")
            isInteractiveChart(chart) -> ReplyBlock.Chart(chart)
            else -> ReplyBlock.Image(chart)
        }
        start = match.range.last + 1
    }
    if (start < content.length || blocks.isEmpty()) blocks += ReplyBlock.Text(content.substring(start))
    return blocks
}

@Composable
internal fun InlineChart(attachment: UploadedAttachment, state: AppUiState, viewModel: AppViewModel) {
    LaunchedEffect(attachment.fileId) { viewModel.loadAttachmentPreview(attachment) }
    val preview = state.attachmentPreviews[attachment.fileId]
    var expanded by remember(attachment.fileId) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(attachment.filename, modifier = Modifier.weight(1f), color = SuyuanColors.secondaryText)
            TextButton(onClick = { expanded = true }) { Text("全屏查看") }
        }
        when {
            preview?.error != null -> {
                Text(preview.error, color = SuyuanColors.error)
                TextButton(onClick = { viewModel.loadAttachmentPreview(attachment) }) { Text("重试") }
            }
            preview?.text != null -> ChartSurface(preview.text, Modifier.fillMaxWidth().height(380.dp))
            else -> Text("正在加载图表…", color = SuyuanColors.secondaryText)
        }
    }
    if (expanded) Dialog(onDismissRequest = { expanded = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(color = Color.White, modifier = Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().systemBarsPadding()) {
                TextButton(onClick = { expanded = false }, modifier = Modifier.fillMaxWidth()) { Text("关闭图表") }
                preview?.text?.let { ChartSurface(it, Modifier.fillMaxWidth().weight(1f)) }
            }
        }
    }
}

@Composable
private fun ChartSurface(json: String, modifier: Modifier) {
    var error by remember(json) { mutableStateOf<String?>(null) }
    val valid = remember(json) { runCatching { JSONObject(json) }.isSuccess }
    if (!valid) { Text("图表数据格式错误", color = SuyuanColors.error); return }
    if (error != null) { Text(error!!, color = SuyuanColors.error); return }
    AndroidView(factory = { ChartWebView(it) { error = it } },
        update = { it.render(json) }, onRelease = { it.destroy() }, modifier = modifier)
}

// Only bundled, shared frontend assets run JavaScript. No access tokens, JS bridge or remote navigation.
private class ChartWebView(context: Context, val onFailure: (String) -> Unit) : WebView(context) {
    private var chartJson: String? = null
    private var loaded = false
    init {
        settings.javaScriptEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.useWideViewPort = true
        setBackgroundColor(android.graphics.Color.WHITE)
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = true
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse {
                val path = request.url.path.orEmpty().removePrefix("/")
                if (request.url.host != "chart.suyuan.local" || path.contains("..") ||
                    (path != "chart.html" && !path.startsWith("assets/"))) {
                    return WebResourceResponse("text/plain", "UTF-8", ByteArrayInputStream(ByteArray(0)))
                }
                return try {
                    val mime = when (path.substringAfterLast('.')) {
                        "js", "mjs" -> "application/javascript"
                        "css" -> "text/css"
                        "html" -> "text/html"
                        "svg" -> "image/svg+xml"
                        "png" -> "image/png"
                        "woff2" -> "font/woff2"
                        else -> "application/octet-stream"
                    }
                    WebResourceResponse(mime, "UTF-8", context.assets.open("charts/$path"))
                } catch (_: Exception) {
                    post { onFailure("图表组件加载失败，请重新安装最新版本") }
                    WebResourceResponse("text/plain", "UTF-8", ByteArrayInputStream(ByteArray(0)))
                }
            }
            override fun onPageFinished(view: WebView, url: String) { loaded = true; deliver(0) }
        }
        loadUrl("https://chart.suyuan.local/chart.html")
    }
    fun render(json: String) {
        if (chartJson == json) return
        chartJson = json
        if (loaded) deliver(0)
    }
    private fun deliver(attempt: Int) {
        val payload = chartJson ?: return
        // Quote JSON as data, never concatenate raw object content into executable code.
        evaluateJavascript("Boolean(window.suyuanChartReady && window.renderSuyuanChart)") { ready ->
            if (ready == "true") evaluateJavascript("window.renderSuyuanChart(JSON.parse(${JSONObject.quote(payload)}))", null)
            else if (attempt < 40) postDelayed({ deliver(attempt + 1) }, 250)
            else onFailure("图表组件未能启动")
        }
    }
}
