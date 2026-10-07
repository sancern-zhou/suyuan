package com.suyuan.mobile

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

internal data class ReplyOutcomes(val files: List<UploadedAttachment>, val others: List<UploadedAttachment>)

internal fun replyOutcomes(attachments: List<UploadedAttachment>, placed: Set<String>): ReplyOutcomes {
    val used = attachments.filter { it.fileId in placed }
    val groups = used.map { it.groupId }.filter(String::isNotBlank).toSet()
    val visuals = used.map { it.visualId }.filter(String::isNotBlank).toSet()
    val visible = attachments.distinctBy { it.fileId.ifBlank { it.url } }.filterNot {
        it.fileId in placed || (it.groupId.isNotBlank() && it.groupId in groups) || (it.visualId.isNotBlank() && it.visualId in visuals) ||
            (it.resourceRole.isNotBlank() && it.resourceRole !in setOf("output", "report", "attachment")) ||
            it.resourceKind == "data" || (it.resourceKey == "chart-spec" && !it.interactive) ||
            (!isInteractiveChart(it) && (it.filename.substringAfterLast('.', "").lowercase() in setOf("json", "qmd", "log", "yaml", "yml", "parquet", "sql") ||
            it.mimeType.contains("json", true)))
    }
    val grouped = visible.groupBy { it.groupId.ifBlank { it.fileId.ifBlank { it.url } } }.values.map { members ->
        val primary = members.firstOrNull(::isInteractiveChart)
            ?: members.firstOrNull { it.previewUrl != null }
            ?: members.firstOrNull { it.mimeType == "text/html" }
            ?: members.first()
        val variants = (primary.variants + members.filter { it.fileId != primary.fileId && !isImageAttachment(it) }.map {
            AttachmentVariant(it.format.ifBlank { it.filename.substringAfterLast('.', "file") }, it.filename, it.mimeType, it.downloadUrl ?: it.url)
        }).distinctBy { it.url }.filterNot { it.url == primary.url || it.url == primary.downloadUrl }
        primary.copy(variants = variants)
    }
    return ReplyOutcomes(grouped.filterNot { isInteractiveChart(it) || isImageAttachment(it) },
        grouped.filter { isInteractiveChart(it) || isImageAttachment(it) })
}

@Composable
internal fun ReplyOutcomeCards(attachments: List<UploadedAttachment>, placed: Set<String>, state: AppUiState, viewModel: AppViewModel) {
    val outcomes = remember(attachments, placed) { replyOutcomes(attachments, placed) }
    val context = LocalContext.current
    var expanded by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp)) {
        outcomes.files.forEach { AttachmentView(it, state, viewModel, context) }
        if (outcomes.others.isNotEmpty()) {
            TextButton(onClick = { expanded = !expanded }) {
                Text("其他成果（${outcomes.others.size}） ${if (expanded) "⌃" else "⌄"}", color = SuyuanColors.secondaryText)
            }
            if (expanded) outcomes.others.forEach {
                if (isInteractiveChart(it)) InlineChart(it, state, viewModel)
                else AttachmentView(it, state, viewModel, context, inlineImage = true)
            }
        }
    }
}
