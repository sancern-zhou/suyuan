package com.suyuan.mobile

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

@Composable
fun AgentQuestionCard(question: AgentQuestionInteraction, busy: Boolean, resolving: Boolean, error: String?,
    onSubmit: (List<AgentQuestionAnswer>) -> Unit, onCancel: () -> Unit) {
    var open by remember(question.interactionId) { mutableStateOf(true) }
    var index by remember(question.interactionId) { mutableIntStateOf(0) }
    var answers by remember(question.interactionId) { mutableStateOf(question.questions.map { AgentQuestionAnswer() }) }
    Surface(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp), shape = RoundedCornerShape(16.dp),
        color = SuyuanColors.primary.copy(alpha = .06f), border = BorderStroke(1.dp, SuyuanColors.primary.copy(alpha = .18f))) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(question.title, fontWeight = FontWeight.SemiBold, color = SuyuanColors.text)
                Text("${question.questions.size} 个问题，回答后继续原任务", fontSize = 12.sp, color = SuyuanColors.secondaryText)
            }
            TextButton(onClick = { open = true }) { Text("回答问题") }
        }
    }
    if (!open) return
    Dialog(onDismissRequest = { if (!resolving) open = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().imePadding().navigationBarsPadding(), contentAlignment = Alignment.BottomCenter) {
            Surface(modifier = Modifier.fillMaxWidth().fillMaxHeight(.82f), color = Color.White,
                shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)) {
                Column(Modifier.padding(horizontal = 18.dp, vertical = 12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(question.title, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = SuyuanColors.text)
                            Text("问题 ${index + 1}/${question.questions.size}", color = SuyuanColors.secondaryText, fontSize = 12.sp)
                        }
                        TextButton(onClick = { open = false }, enabled = !resolving) { Text("稍后回答") }
                    }
                    val item = question.questions[index]
                    val answer = answers[index]
                    fun update(value: AgentQuestionAnswer) { answers = answers.toMutableList().also { it[index] = value } }
                    key(index) {
                        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(item.question, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = SuyuanColors.text)
                            Text(if (item.multiSelect) "可以选择多项" else "请选择一项", fontSize = 12.sp, color = SuyuanColors.secondaryText)
                            item.options.forEachIndexed { optionIndex, option ->
                                QuestionOptionRow(option.label, option.description, option.preview,
                                    optionIndex in answer.selected, item.multiSelect, !resolving) {
                                    update(answer.select(optionIndex, item.multiSelect))
                                }
                            }
                            QuestionOptionRow("其他", "填写你的选择", "", answer.customEnabled, item.multiSelect, !resolving) {
                                update(answer.selectCustom(item.multiSelect))
                            }
                            if (answer.customEnabled) OutlinedTextField(value = answer.custom,
                                onValueChange = { if (it.length <= 4000) update(answer.copy(custom = it)) },
                                placeholder = { Text("请输入你的选择") }, minLines = 2, maxLines = 5,
                                enabled = !resolving, modifier = Modifier.fillMaxWidth())
                            Spacer(Modifier.height(8.dp))
                        }
                    }
                    if (error != null) Text(error, color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
                    if (busy) Text("正在保存问题，请稍候…", color = SuyuanColors.secondaryText, fontSize = 12.sp)
                    Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (index > 0) TextButton(onClick = { index-- }, enabled = !resolving) { Text("上一题") }
                        else TextButton(onClick = onCancel, enabled = !busy && !resolving) { Text("取消本次问题") }
                        Spacer(Modifier.weight(1f))
                        if (index < question.questions.lastIndex) {
                            Button(onClick = { index++ }, enabled = answer.valid(item) && !resolving) { Text("下一题") }
                        } else Button(onClick = { onSubmit(answers) }, enabled = !busy && !resolving && answers.zip(question.questions).all { it.first.valid(it.second) }) {
                            Text(if (resolving) "提交中…" else "提交并继续")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun QuestionOptionRow(label: String, description: String, preview: String, selected: Boolean,
    multiple: Boolean, enabled: Boolean, onClick: () -> Unit) {
    Surface(modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(12.dp), color = if (selected) SuyuanColors.primary.copy(alpha = .07f) else Color.White,
        border = BorderStroke(1.dp, if (selected) SuyuanColors.primary else Color(0xFFE7E9EE))) {
        Row(Modifier.padding(end = 12.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            if (multiple) Checkbox(selected, onCheckedChange = null, enabled = enabled, modifier = Modifier.size(44.dp))
            else RadioButton(selected, onClick = null, enabled = enabled, modifier = Modifier.size(44.dp))
            Column(Modifier.weight(1f)) {
                Text(label, fontWeight = FontWeight.Medium, fontSize = 15.sp, color = SuyuanColors.text)
                if (description.isNotBlank()) Text(description, fontSize = 12.sp, color = SuyuanColors.secondaryText)
                if (preview.isNotBlank()) Text(preview, fontSize = 12.sp, color = SuyuanColors.secondaryText, maxLines = 5, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}
