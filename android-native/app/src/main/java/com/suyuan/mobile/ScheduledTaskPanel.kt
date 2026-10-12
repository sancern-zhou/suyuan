package com.suyuan.mobile

import android.app.DatePickerDialog
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import org.json.JSONObject
import java.util.Calendar

@Composable
fun ScheduledTaskPanel(state: AppUiState, viewModel: AppViewModel, requestedTaskId: String?, onSession: () -> Unit) {
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var start by rememberSaveable { mutableStateOf("") }
    var end by rememberSaveable { mutableStateOf("") }
    var station by rememberSaveable { mutableStateOf("") }
    var pollutant by rememberSaveable { mutableStateOf("") }
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var filtersExpanded by rememberSaveable { mutableStateOf(false) }
    var reportUrl by remember { mutableStateOf<String?>(null) }
    val selected = state.scheduledTasks.firstOrNull { it.taskId == selectedId }
    fun reload(page: Int = 1) { selectedId?.let { viewModel.queryTaskResults(it, page, start, end, station, pollutant) } }
    LaunchedEffect(state.scheduledTasks, requestedTaskId) {
        val target = requestedTaskId ?: selectedId ?: state.scheduledTasks.firstOrNull()?.taskId
        if (target != null && target != selectedId) {
            selectedId = target
            start = ""; end = ""; station = ""; pollutant = ""
            viewModel.queryTaskResults(target)
        }
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        Row(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton(onClick = { filtersExpanded = !filtersExpanded }, enabled = selectedId != null) { Text(if (filtersExpanded) "收起筛选" else "筛选执行记录") }
            TextButton(onClick = { reload() }, enabled = selectedId != null) { Text("刷新") }
        }
        state.taskError?.let { Text(it, color = Color(0xFFB42318), fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp)) }
        if (selectedId == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            if (filtersExpanded) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TaskDateFilter("开始日期", start, { start = it }, Modifier.weight(1f))
                TaskDateFilter("结束日期", end, { end = it }, Modifier.weight(1f))
            }
            val stations = state.taskFacets.optJSONArray("stations") ?: org.json.JSONArray()
            val pollutants = state.taskFacets.optJSONArray("pollutants") ?: org.json.JSONArray()
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                TaskOptionFilter("站点", station, (0 until stations.length()).mapNotNull { stations.optJSONObject(it)?.let { v -> v.optString("station_id") to v.optString("station_name", v.optString("station_id")) } }, { station = it }, Modifier.weight(1f))
                TaskOptionFilter("污染物", pollutant, (0 until pollutants.length()).map { pollutants.optString(it) to pollutants.optString(it) }, { pollutant = it }, Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = { start = ""; end = ""; station = ""; pollutant = ""; reload() }) { Text("重置") }
                TextButton(onClick = { reload() }, enabled = !state.taskResultsLoading) { Text("查询") }
            }
            }
            if (state.taskResultsLoading) CircularProgressIndicator(Modifier.padding(16.dp))
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(14.dp), contentPadding = PaddingValues(vertical = 10.dp)) {
                if (state.taskResults.isEmpty() && !state.taskResultsLoading && state.taskError == null) item { Text("暂无符合条件的执行结果", Modifier.padding(16.dp)) }
                items(state.taskResults, key = { it.optString("execution_id") }) { record ->
                    Surface(color = Color.White, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth().border(1.dp, Color(0xFFE5E7EB), RoundedCornerShape(14.dp))) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(record.text("completed_at").ifBlank { record.text("started_at") }.replace('T', ' ').take(16), fontSize = 13.sp, color = Color.Gray)
                            Text(taskStatusLabel(record.text("status")), fontSize = 13.sp, color = Color(0xFF007AFF))
                            val location = listOf(record.text("city"), record.text("station_name").ifBlank { record.text("station_id") }, record.text("pollutant")).filter { it.isNotBlank() }.joinToString(" · ")
                            if (location.isNotBlank()) Text(location, fontSize = 14.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium)
                            Text(record.text("conclusion").ifBlank { "暂无结论" }, fontSize = 14.sp, lineHeight = 23.sp, maxLines = 4, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                            Text("图片 ${record.optJSONArray("image_paths")?.length() ?: 0} 个 · 文档 ${record.optJSONArray("document_paths")?.length() ?: 0} 个", fontSize = 12.sp, color = Color.Gray)
                            TextButton(onClick = { detail = record }, modifier = Modifier.fillMaxWidth()) { Text(if (record.optBoolean("has_broadcast")) "查看完整结论与广播" else "查看完整结论") }
                            if (record.optBoolean("has_report")) OutlinedButton(onClick = { reportUrl = BuildConfig.API_BASE_URL.trimEnd('/') + "/api/scheduled-tasks/results/${record.text("execution_id")}/report/_t/${record.text("preview_ticket")}/report.html" }, modifier = Modifier.fillMaxWidth()) { Text("查看报告") }
                            val session = record.text("session_id")
                            if (session.isNotBlank()) OutlinedButton(onClick = { viewModel.loadSession(SessionInfo(session, "expert", selected?.name ?: "任务会话")); onSession() }, modifier = Modifier.fillMaxWidth()) { Text("进入会话") }
                        }
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = { reload(state.taskPage - 1) }, enabled = state.taskPage > 1 && !state.taskResultsLoading) { Text("上一页") }
                Text("${state.taskPage}/${state.taskTotalPages.coerceAtLeast(1)} 页 · 共 ${state.taskTotal} 条", fontSize = 12.sp, modifier = Modifier.padding(top = 14.dp))
                TextButton(onClick = { reload(state.taskPage + 1) }, enabled = state.taskPage < state.taskTotalPages && !state.taskResultsLoading) { Text("下一页") }
            }
        }
    }
    detail?.let { record ->
        Dialog(onDismissRequest = { detail = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(Modifier.fillMaxWidth().fillMaxHeight(.85f).padding(12.dp), shape = RoundedCornerShape(16.dp), color = Color.White) {
                Column(Modifier.padding(16.dp)) {
                    TextButton(onClick = { detail = null }) { Text("关闭详情") }
                    Column(Modifier.verticalScroll(rememberScrollState())) {
                        MarkdownContent(record.text("conclusion"), Color(0xFF202124))
                        if (record.optBoolean("has_broadcast")) {
                            Text("广播内容", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(vertical = 12.dp))
                            MarkdownContent(record.text("broadcast_message"), Color(0xFF202124))
                            val images = record.optJSONArray("broadcast_image_urls") ?: org.json.JSONArray()
                            for (i in 0 until images.length()) {
                                val attachment = UploadedAttachment.fromJson(JSONObject().put("file_id", "${record.text("execution_id")}-broadcast-$i").put("filename", "广播图片${i + 1}.png").put("mime_type", "image/png").put("url", images.optString(i)))
                                AttachmentView(attachment, state, viewModel, LocalContext.current)
                            }
                        }
                    }
                }
            }
        }
    }
    reportUrl?.let { target ->
        var downloads by remember(target) { mutableStateOf<List<UploadedAttachment>>(emptyList()) }
        var formatsLoading by remember(target) { mutableStateOf(true) }
        var downloadError by remember(target) { mutableStateOf<String?>(null) }
        var downloading by remember(target) { mutableStateOf<String?>(null) }
        var reloadFormats by remember(target) { mutableStateOf(0) }
        val downloadContext = LocalContext.current
        LaunchedEffect(target, reloadFormats) {
            formatsLoading = true
            downloadError = null
            try {
                downloads = viewModel.reportDownloadFormats(target.substringAfter("/results/").substringBefore("/report/"))
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                downloadError = failure.message ?: "下载格式加载失败"
            } finally { formatsLoading = false }
        }
        Dialog(onDismissRequest = { reportUrl = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(Modifier.fillMaxSize().padding(8.dp), color = Color.White) {
                Column {
                    TextButton(onClick = { reportUrl = null }) { Text("关闭报告") }
                    Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf("docx" to "Word", "html" to "HTML").forEach { (format, label) ->
                            val file = downloads.firstOrNull { it.format == format }
                            OutlinedButton(modifier = Modifier.weight(1f), enabled = file != null && !formatsLoading && downloading == null,
                                onClick = {
                                    file?.let {
                                        downloading = format
                                        viewModel.downloadAttachment(downloadContext, it) { success ->
                                            downloading = null
                                            android.widget.Toast.makeText(downloadContext, if (success) "已保存到下载/许昌环境Agent" else "下载失败，请重试", android.widget.Toast.LENGTH_LONG).show()
                                        }
                                    }
                                }) {
                                Text(if (downloading == format) "下载中…" else "下载 $label", fontSize = 13.sp)
                            }
                        }
                    }
                    if (formatsLoading) Text("正在加载下载格式…", fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp))
                    else if (downloadError != null) Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Text(downloadError.orEmpty(), color = Color(0xFFB42318), fontSize = 12.sp, modifier = Modifier.weight(1f).padding(start = 16.dp))
                        TextButton(onClick = { reloadFormats++ }) { Text("重试") }
                    }
                    else if (downloads.none { it.format == "docx" }) Text("此报告尚未生成 Word 文件", fontSize = 12.sp, color = Color.Gray, modifier = Modifier.padding(horizontal = 16.dp))
                    AndroidView(factory = { WebView(it).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.useWideViewPort = false
                        settings.loadWithOverviewMode = false
                        settings.builtInZoomControls = true
                        settings.displayZoomControls = false
                        webViewClient = object : WebViewClient() {
                            override fun onPageFinished(view: WebView, url: String) {
                                super.onPageFinished(view, url)
                                view.evaluateJavascript(MOBILE_REPORT_STYLE, null)
                            }
                        }
                        loadUrl(target)
                    } }, modifier = Modifier.weight(1f).fillMaxWidth())
                }
            }
        }
    }
}

private val MOBILE_REPORT_STYLE = """
(function(){
  var viewport=document.querySelector('meta[name=viewport]');
  if(!viewport){viewport=document.createElement('meta');viewport.name='viewport';document.head.appendChild(viewport);}
  viewport.content='width=device-width,initial-scale=1,maximum-scale=5,viewport-fit=cover';
  var style=document.getElementById('suyuan-mobile-report-style');
  if(!style){style=document.createElement('style');style.id='suyuan-mobile-report-style';document.head.appendChild(style);}
  style.textContent=`
    html,body{width:100%!important;max-width:100%!important;margin:0!important;padding:0!important;overflow-x:hidden!important;background:#fff!important}
    body{font-size:16px!important;line-height:1.75!important;color:#202124!important}
    *,*::before,*::after{box-sizing:border-box}
    #quarto-content,.page-columns,.page-rows{display:block!important;grid-template-columns:none!important;column-count:1!important;width:100%!important;max-width:100%!important;margin:0!important;padding:0!important}
    main,main.content{display:block!important;float:none!important;column-count:1!important;width:100%!important;min-width:0!important;max-width:100%!important;margin:0!important;padding:16px!important}
    main p,main section,main .columns,main .column{float:none!important;column-count:1!important;width:auto!important;min-width:0!important;max-width:100%!important}
    main .columns{display:block!important}
    #quarto-sidebar,.sidebar,.margin-sidebar,.page-navigation{display:none!important}
    h1,h2,h3,h4{line-height:1.35!important;overflow-wrap:anywhere!important}
    p,li,td,th{overflow-wrap:anywhere!important;word-break:break-word!important}
    img,svg,video,canvas{max-width:100%!important;height:auto!important}
    .suyuan-report-table-scroll{display:block;width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;margin:12px 0}
    table{width:100%!important;min-width:600px!important;max-width:none!important;font-size:13px!important}
    table thead th,table tbody td{white-space:normal!important;min-width:72px!important}
    .table-responsive,.table-scroll,.table-container,table{overflow-x:auto!important}
    pre,code{white-space:pre-wrap!important;overflow-wrap:anywhere!important}
    .quarto-figure,.figure,.cell-output-display{max-width:100%!important;overflow-x:auto!important}
  `;
  document.querySelectorAll('table').forEach(function(table){
    if(table.parentElement.classList.contains('suyuan-report-table-scroll'))return;
    var wrapper=document.createElement('div');wrapper.className='suyuan-report-table-scroll';
    table.parentNode.insertBefore(wrapper,table);wrapper.appendChild(table);
  });
  window.dispatchEvent(new Event('resize'));
})()
""".trimIndent()

private fun JSONObject.text(key: String) = optString(key).takeIf { it != "null" }.orEmpty()
private fun taskTypeLabel(value: String) = when (value) { "event" -> "事件任务"; "schedule", "scheduled" -> "定时任务"; else -> value }
private fun taskStatusLabel(value: String) = when (value) { "success", "completed" -> "成功"; "failed", "error" -> "失败"; "running" -> "执行中"; else -> value }
@Composable
private fun TaskDateFilter(label: String, value: String, onChange: (String) -> Unit, modifier: Modifier) {
    val context = LocalContext.current
    TextButton(onClick = {
        val now = Calendar.getInstance()
        DatePickerDialog(context, { _, year, month, day -> onChange("%04d-%02d-%02d".format(year, month + 1, day)) }, now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH)).show()
    }, modifier = modifier.border(1.dp, Color(0xFFE5E7EB), RoundedCornerShape(8.dp))) { Text(value.ifBlank { label }, fontSize = 12.sp) }
}
@Composable
private fun TaskOptionFilter(label: String, value: String, options: List<Pair<String, String>>, onChange: (String) -> Unit, modifier: Modifier) {
    var expanded by remember { mutableStateOf(false) }
    Box(modifier) {
        TextButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth().border(1.dp, Color(0xFFE5E7EB), RoundedCornerShape(8.dp))) { Text(options.firstOrNull { it.first == value }?.second ?: "全部$label", fontSize = 12.sp) }
        DropdownMenu(expanded, { expanded = false }) {
            (listOf("" to "全部$label") + options).forEach { (id, text) -> DropdownMenuItem(text = { Text(text) }, onClick = { onChange(id); expanded = false }) }
        }
    }
}
