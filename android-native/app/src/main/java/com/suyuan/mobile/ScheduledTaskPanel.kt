package com.suyuan.mobile

import android.app.DatePickerDialog
import android.webkit.WebView
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
fun ScheduledTaskPanel(state: AppUiState, viewModel: AppViewModel, onSession: () -> Unit) {
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var type by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var start by rememberSaveable { mutableStateOf("") }
    var end by rememberSaveable { mutableStateOf("") }
    var station by rememberSaveable { mutableStateOf("") }
    var pollutant by rememberSaveable { mutableStateOf("") }
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var reportUrl by remember { mutableStateOf<String?>(null) }
    val selected = state.scheduledTasks.firstOrNull { it.taskId == selectedId }
    fun reload(page: Int = 1) { selectedId?.let { viewModel.queryTaskResults(it, page, start, end, station, pollutant) } }
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        Row(Modifier.fillMaxWidth()) {
            Text(selected?.name?.let { "$it · 执行记录" } ?: "任务工作区", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(top = 12.dp))
            TextButton(onClick = { if (selectedId == null) viewModel.refreshScheduledTasks() else reload() }) { Text("刷新") }
            if (selectedId != null) TextButton(onClick = { selectedId = null }) { Text("返回") }
        }
        state.taskError?.let { Text(it, color = Color(0xFFB42318), fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp)) }
        if (selectedId == null) {
            Text("${state.scheduledTasks.size} 个任务 · ${state.scheduledTasks.count { it.enabled }} 个已启用", fontSize = 12.sp, color = Color.Gray)
            OutlinedTextField(query, { query = it }, label = { Text("搜索任务名称或描述") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
            Row(Modifier.horizontalScroll(rememberScrollState())) {
                (listOf("") + state.scheduledTasks.map { it.taskType }.distinct()).forEach { key ->
                    FilterChip(selected = type == key, onClick = { type = key }, label = { Text(if (key.isBlank()) "全部类型" else taskTypeLabel(key)) }, modifier = Modifier.padding(end = 6.dp))
                }
            }
            if (state.scheduledTasksLoading) CircularProgressIndicator(Modifier.padding(16.dp))
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
                val tasks = state.scheduledTasks.filter { (type.isBlank() || it.taskType == type) && (query.isBlank() || it.name.contains(query, true) || it.description.contains(query, true)) }
                if (tasks.isEmpty() && !state.scheduledTasksLoading && state.taskError == null) item { Text("暂无可查看的任务", color = Color.Gray) }
                items(tasks, key = { it.taskId }) { task ->
                    Surface(color = Color.White, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth().border(1.dp, Color(0xFFE5E7EB), RoundedCornerShape(12.dp))) {
                        Column(Modifier.padding(14.dp)) {
                            Row { Text(task.name, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, modifier = Modifier.weight(1f)); Text(if (task.enabled) "已启用" else "已停用", fontSize = 12.sp, color = Color.Gray) }
                            Text(taskTypeLabel(task.taskType), color = Color(0xFF007AFF), fontSize = 12.sp, modifier = Modifier.padding(vertical = 6.dp))
                            if (task.description.isNotBlank()) Text(task.description, fontSize = 13.sp, color = Color.Gray)
                            Text("成功 ${task.successRuns}/${task.totalRuns} · 下次执行 ${task.nextRunAt?.replace('T', ' ')?.take(16) ?: "—"}", fontSize = 11.sp, color = Color.Gray, modifier = Modifier.padding(top = 8.dp))
                            TextButton(onClick = { selectedId = task.taskId; start = ""; end = ""; station = ""; pollutant = ""; viewModel.queryTaskResults(task.taskId) }) { Text("查看执行记录") }
                        }
                    }
                }
            }
        } else {
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
            Text("左右滑动查看完整列表", fontSize = 11.sp, color = Color.Gray)
            if (state.taskResultsLoading) CircularProgressIndicator(Modifier.padding(16.dp))
            Column(Modifier.weight(1f).horizontalScroll(rememberScrollState()).width(1100.dp)) {
                Row(Modifier.background(Color(0xFFF3F5F8)).padding(vertical = 10.dp)) {
                    listOf("时间" to 145, "状态" to 75, "城市" to 70, "站点" to 130, "污染物" to 75, "结论" to 340, "产物" to 80, "操作" to 185).forEach { (label, width) -> TaskCell(label, width) }
                }
                LazyColumn {
                    if (state.taskResults.isEmpty() && !state.taskResultsLoading && state.taskError == null) item { Text("暂无符合条件的执行结果", Modifier.padding(16.dp)) }
                    items(state.taskResults, key = { it.optString("execution_id") }) { record ->
                        Row(Modifier.fillMaxWidth().border(.5.dp, Color(0xFFE5E7EB)).padding(vertical = 10.dp)) {
                            TaskCell(record.text("completed_at").ifBlank { record.text("started_at") }.replace('T', ' ').take(16), 145)
                            TaskCell(taskStatusLabel(record.text("status")), 75)
                            TaskCell(record.text("city"), 70)
                            TaskCell(record.text("station_name").ifBlank { record.text("station_id") }, 130)
                            TaskCell(record.text("pollutant"), 75)
                            TaskCell(record.text("conclusion").take(300), 340)
                            TaskCell("图 ${record.optJSONArray("image_paths")?.length() ?: 0}\n文 ${record.optJSONArray("document_paths")?.length() ?: 0}", 80)
                            Column(Modifier.width(185.dp)) {
                                if (record.optBoolean("has_report")) TextButton(onClick = { reportUrl = BuildConfig.API_BASE_URL.trimEnd('/') + "/api/scheduled-tasks/results/${record.text("execution_id")}/report/_t/${record.text("preview_ticket")}/report.html" }) { Text("查看报告") }
                                TextButton(onClick = { detail = record }) { Text(if (record.optBoolean("has_broadcast")) "结论 / 广播内容" else "查看结论") }
                                val session = record.text("session_id")
                                if (session.isNotBlank()) TextButton(onClick = { viewModel.loadSession(SessionInfo(session, "expert", selected?.name ?: "任务会话")); onSession() }) { Text("进入会话") }
                            }
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
        Dialog(onDismissRequest = { reportUrl = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(Modifier.fillMaxSize().padding(8.dp), color = Color.White) {
                Column {
                    TextButton(onClick = { reportUrl = null }) { Text("关闭报告") }
                    AndroidView(factory = { WebView(it).apply { settings.javaScriptEnabled = false; loadUrl(target) } }, modifier = Modifier.weight(1f).fillMaxWidth())
                }
            }
        }
    }
}

private fun JSONObject.text(key: String) = optString(key).takeIf { it != "null" }.orEmpty()
private fun taskTypeLabel(value: String) = when (value) { "event" -> "事件任务"; "schedule", "scheduled" -> "定时任务"; else -> value }
private fun taskStatusLabel(value: String) = when (value) { "success", "completed" -> "成功"; "failed", "error" -> "失败"; "running" -> "执行中"; else -> value }
@Composable
private fun TaskCell(value: String, width: Int) { Text(value.ifBlank { "—" }, Modifier.width(width.dp).padding(horizontal = 8.dp), fontSize = 12.sp, lineHeight = 18.sp) }
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
