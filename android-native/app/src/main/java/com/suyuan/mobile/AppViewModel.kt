package com.suyuan.mobile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import android.content.Context
import android.net.Uri
import android.content.ContentValues
import android.os.Environment
import android.os.Build
import android.provider.MediaStore
import java.util.ArrayDeque
import java.util.UUID

data class AttachmentPreview(
    val loading: Boolean = false,
    val text: String? = null,
    val imageBytes: ByteArray? = null,
    val pdfBytes: ByteArray? = null,
    val error: String? = null,
)

data class AppUiState(
    val token: String = "",
    val accountId: String = "",
    val displayName: String = "",
    val sessionId: String? = null,
    val sessions: List<SessionInfo> = emptyList(),
    val draft: String = "",
    val messages: List<ChatMessage> = emptyList(),
    val attachments: List<UploadedAttachment> = emptyList(),
    val expandedAttachments: Set<String> = emptySet(),
    val attachmentPreviews: Map<String, AttachmentPreview> = emptyMap(),
    val loading: Boolean = false,
    val error: String? = null,
) {
    val loggedIn: Boolean get() = token.isNotBlank()
}

private data class PendingTurn(
    val query: String,
    val attachments: List<UploadedAttachment>,
    val sessionId: String?,
)

class AppViewModel(
    private val repository: SocialAppRepository,
    private val store: AppSessionStore,
) : ViewModel() {
    private val _state = MutableStateFlow(
        AppUiState(store.token(), store.accountId(), store.displayName())
    )
    val state: StateFlow<AppUiState> = _state.asStateFlow()
    private var streamJob: Job? = null
    private val pendingTurns = ArrayDeque<PendingTurn>()

    init {
        if (_state.value.loggedIn) refreshSessions()
    }

    fun updateDraft(value: String) = _state.value.let { _state.value = it.copy(draft = value, error = null) }

    fun newConversation() {
        // Do not cancel an in-flight turn from the previous session. Its
        // stream continues to be persisted in the background and is ignored
        // by the new conversation UI until the user reopens that session.
        val current = _state.value
        _state.value = current.copy(sessionId = null, draft = "", messages = emptyList(), attachments = emptyList(), error = null, loading = false)
        viewModelScope.launch {
            runCatching { repository.createSession(current.token) }
                .onSuccess { session ->
                    if (_state.value.sessionId == null && _state.value.messages.isEmpty()) {
                        _state.value = _state.value.copy(sessionId = session.sessionId)
                    }
                    _state.value = _state.value.copy(sessions = listOf(session) + _state.value.sessions.filterNot { it.sessionId == session.sessionId })
                }
                .onFailure { _state.value = _state.value.copy(error = "已进入新对话，服务端会在首次发送时创建会话") }
        }
    }

    fun loadSession(session: SessionInfo) {
        val current = _state.value
        if (current.loading) return
        _state.value = current.copy(sessionId = session.sessionId, draft = "", messages = emptyList(), attachments = emptyList(), loading = true, error = null)
        viewModelScope.launch {
            runCatching { repository.messages(current.token, session.sessionId) }
                .onSuccess { messages -> _state.value = _state.value.copy(messages = messages, loading = false) }
                .onFailure { _state.value = _state.value.copy(loading = false, error = friendlyError(it)) }
        }
    }

    fun renameSession(session: SessionInfo, title: String) {
        val cleanTitle = title.trim()
        if (cleanTitle.isBlank()) return
        val current = _state.value
        viewModelScope.launch {
            runCatching { repository.renameSession(current.token, session.sessionId, cleanTitle) }
                .onSuccess {
                    _state.value = _state.value.copy(
                        sessions = _state.value.sessions.map { item ->
                            if (item.sessionId == session.sessionId) item.copy(title = cleanTitle) else item
                        },
                    )
                }
                .onFailure { failure ->
                    if (failure is ApiException && failure.statusCode == 401) logout("登录已过期，请重新登录")
                    else _state.value = _state.value.copy(error = friendlyError(failure))
                }
        }
    }

    fun deleteSession(session: SessionInfo) {
        val current = _state.value
        viewModelScope.launch {
            runCatching { repository.deleteSession(current.token, session.sessionId) }
                .onSuccess {
                    val remaining = _state.value.sessions.filterNot { it.sessionId == session.sessionId }
                    _state.value = _state.value.copy(
                        sessions = remaining,
                        sessionId = if (_state.value.sessionId == session.sessionId) null else _state.value.sessionId,
                        messages = if (_state.value.sessionId == session.sessionId) emptyList() else _state.value.messages,
                    )
                }
                .onFailure { failure ->
                    if (failure is ApiException && failure.statusCode == 401) logout("登录已过期，请重新登录")
                    else _state.value = _state.value.copy(error = friendlyError(failure))
                }
        }
    }

    fun login(accountId: String, secret: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            runCatching { repository.login(accountId, secret) }
                .onSuccess { result ->
                    store.save(result)
                    _state.value = AppUiState(result.token, result.accountId, result.displayName, loading = false)
                    refreshSessions()
                }
                .onFailure { _state.value = _state.value.copy(loading = false, error = friendlyError(it)) }
        }
    }

    fun send() {
        val current = _state.value
        val query = current.draft.trim()
        if (query.isEmpty() || !current.loggedIn) return
        val userMessage = ChatMessage(
            id = UUID.randomUUID().toString(),
            kind = "user",
            content = query,
            attachments = current.attachments,
        )
        _state.value = current.copy(
            draft = "",
            loading = true,
            error = null,
            attachments = emptyList(),
            messages = current.messages + userMessage,
        )
        pendingTurns.addLast(PendingTurn(query, current.attachments.toList(), current.sessionId))
        ensureStreamWorker()
    }

    /** Processes turns sequentially so rapid sends keep session history ordered. */
    private fun ensureStreamWorker() {
        if (streamJob?.isActive == true) return
        streamJob = viewModelScope.launch {
            while (pendingTurns.isNotEmpty()) {
                runTurn(pendingTurns.removeFirst())
            }
            streamJob = null
            if (pendingTurns.isNotEmpty()) {
                _state.value = _state.value.copy(loading = true)
                ensureStreamWorker()
            } else {
                _state.value = _state.value.copy(loading = false)
            }
        }
    }

    private suspend fun runTurn(turn: PendingTurn) {
        val current = _state.value
        var turnSessionId = turn.sessionId
        var thoughtId: String? = null
        var answerId: String? = null
        var outputAttachments: List<UploadedAttachment> = emptyList()
        runCatching {
            repository.stream(current.token, turn.query, turnSessionId, turn.attachments).collect { event ->
                if (event.type == "start") {
                    val session = runCatching { org.json.JSONObject(event.data).optString("session_id") }.getOrNull()
                    if (!session.isNullOrBlank() && turnSessionId == null) {
                        turnSessionId = session
                        if (_state.value.sessionId == null) {
                            _state.value = _state.value.copy(sessionId = session)
                        }
                    }
                }
                // Continue consuming old-session events so the backend can
                // persist them, but never let them mutate the active session UI.
                if (_state.value.sessionId != turnSessionId) return@collect
                when (event.type) {
                    "start" -> {
                        // Session selection is handled before this guard.
                    }
                    "thought" -> {
                        val data = runCatching { org.json.JSONObject(event.data) }.getOrNull()
                        val content = data?.optString("thought").orEmpty().trim()
                        // The backend may emit a progress-only thought event. Do not
                        // create a visible row until there is real reasoning text.
                        if (isVisibleThought(content)) {
                            thoughtId = thoughtId ?: UUID.randomUUID().toString()
                            upsertMessage(ChatMessage(thoughtId!!, "thought", content, expanded = false))
                        }
                    }
                    "thinking_delta" -> {
                        val data = runCatching { org.json.JSONObject(event.data) }.getOrNull()
                        val chunk = data?.optString("chunk").orEmpty()
                        if (chunk.trim().isNotEmpty()) {
                            thoughtId = thoughtId ?: UUID.randomUUID().toString()
                            if (_state.value.messages.none { it.id == thoughtId }) {
                                upsertMessage(ChatMessage(thoughtId!!, "thought", chunk, expanded = false))
                            } else {
                                updateMessage(thoughtId!!) { it.copy(content = it.content + chunk) }
                            }
                        }
                    }
                    "thinking_content" -> {
                        // The backend emits this aggregate form for providers
                        // that expose reasoning only when a thinking block closes.
                        // Merge it into the same mobile thought row used by deltas.
                        val data = runCatching { org.json.JSONObject(event.data) }.getOrNull()
                        val content = data?.optString("content").orEmpty().trim()
                        if (isVisibleThought(content)) {
                            thoughtId = thoughtId ?: UUID.randomUUID().toString()
                            val existing = _state.value.messages.firstOrNull { it.id == thoughtId }
                            if (existing == null) {
                                upsertMessage(ChatMessage(thoughtId!!, "thought", content, expanded = false))
                            } else if (content.length >= existing.content.length) {
                                updateMessage(thoughtId!!) { it.copy(content = content) }
                            }
                        }
                    }
                    "resources_changed" -> {
                        val data = runCatching { org.json.JSONObject(event.data) }.getOrNull()
                        val incoming = data?.let { parseAttachments(it) }.orEmpty()
                        if (incoming.isNotEmpty()) {
                            outputAttachments = mergeAttachments(outputAttachments, incoming)
                            if (answerId != null) {
                                updateMessage(answerId!!) { it.copy(attachments = mergeAttachments(it.attachments, incoming)) }
                            }
                        }
                    }
                    // Tool calls/results are intentionally hidden in the mobile view.
                    "tool_use", "tool_result" -> Unit
                    "streaming_text" -> {
                        val data = runCatching { org.json.JSONObject(event.data) }.getOrNull()
                        val chunk = data?.optString("chunk").orEmpty()
                        if (chunk.isNotEmpty()) {
                            answerId = answerId ?: UUID.randomUUID().toString()
                            if (_state.value.messages.none { it.id == answerId }) {
                                upsertMessage(ChatMessage(answerId!!, "assistant", chunk, streaming = true))
                            } else {
                                updateMessage(answerId!!) { it.copy(content = it.content + chunk, streaming = true) }
                            }
                        }
                        if (data?.optBoolean("is_complete") == true && answerId != null) {
                            updateMessage(answerId!!) { it.copy(streaming = false) }
                        }
                    }
                    "complete" -> {
                        val data = runCatching { org.json.JSONObject(event.data) }.getOrNull()
                        val answer = data?.optString("answer").orEmpty()
                        val incomingAttachments = mergeAttachments(outputAttachments, data?.let { parseAttachments(it) }.orEmpty())
                        if (answer.isNotBlank()) {
                            answerId = answerId ?: UUID.randomUUID().toString()
                            if (_state.value.messages.none { it.id == answerId }) {
                                upsertMessage(ChatMessage(answerId!!, "assistant", answer, incomingAttachments, streaming = false))
                            } else {
                                updateMessage(answerId!!) { it.copy(content = answer, attachments = if (incomingAttachments.isEmpty()) it.attachments else incomingAttachments, streaming = false) }
                            }
                        } else if (answerId != null) {
                            updateMessage(answerId!!) { it.copy(streaming = false) }
                        }
                        if (answer.isBlank() && incomingAttachments.isNotEmpty()) {
                            upsertMessage(ChatMessage(UUID.randomUUID().toString(), "assistant", "", incomingAttachments))
                        }
                        collapseThoughts()
                    }
                    "fatal_error", "incomplete", "interrupted" -> {
                        val data = runCatching { org.json.JSONObject(event.data) }.getOrNull()
                        val error = data?.optString("error").orEmpty()
                            .ifBlank { data?.optString("reason").orEmpty() }
                            .ifBlank { data?.optString("message").orEmpty() }
                        if (error.isNotBlank()) upsertMessage(ChatMessage(UUID.randomUUID().toString(), "error", error))
                        collapseThoughts()
                    }
                }
            }
        }.onFailure { failure ->
            if (failure is kotlinx.coroutines.CancellationException) throw failure
            if (failure is ApiException && failure.statusCode == 401) {
                logout("登录已过期，请重新登录")
            } else if (_state.value.sessionId == turnSessionId) {
                _state.value = _state.value.copy(error = friendlyError(failure))
            }
        }
        if (answerId != null && _state.value.sessionId == turnSessionId) updateMessage(answerId!!) { it.copy(streaming = false) }
    }

    private fun upsertMessage(message: ChatMessage) {
        val current = _state.value
        val index = current.messages.indexOfFirst { it.id == message.id }
        _state.value = if (index < 0) current.copy(messages = current.messages + message) else {
            val updated = current.messages.toMutableList()
            updated[index] = message
            current.copy(messages = updated)
        }
    }

    private fun updateMessage(id: String, transform: (ChatMessage) -> ChatMessage) {
        val current = _state.value
        val index = current.messages.indexOfFirst { it.id == id }
        if (index < 0) return
        val updated = current.messages.toMutableList()
        updated[index] = transform(updated[index])
        _state.value = current.copy(messages = updated)
    }

    private fun collapseThoughts() {
        val current = _state.value
        _state.value = current.copy(messages = current.messages.map { if (it.kind == "thought") it.copy(expanded = false) else it })
    }

    private fun parseAttachments(data: org.json.JSONObject): List<UploadedAttachment> {
        val result = linkedMapOf<String, UploadedAttachment>()
        fun collect(array: org.json.JSONArray?) {
            if (array == null) return
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                val attachment = UploadedAttachment.fromJson(item)
                if (attachment.fileId.isNotBlank() || attachment.url.isNotBlank()) {
                    result[attachment.fileId.ifBlank { attachment.url }] = attachment
                }
            }
        }
        collect(data.optJSONArray("attachments"))
        collect(data.optJSONArray("files"))
        collect(data.optJSONArray("resources"))
        data.optJSONObject("result")?.let { nested ->
            collect(nested.optJSONArray("attachments"))
            collect(nested.optJSONArray("files"))
            collect(nested.optJSONArray("resources"))
        }
        return result.values.toList()
    }

    private fun mergeAttachments(first: List<UploadedAttachment>, second: List<UploadedAttachment>): List<UploadedAttachment> {
        val merged = linkedMapOf<String, UploadedAttachment>()
        (first + second).forEach { item ->
            val key = item.fileId.ifBlank { item.url }.ifBlank { item.filename }
            if (key.isNotBlank()) merged[key] = item
        }
        return merged.values.toList()
    }

    fun toggleThought(id: String) = updateMessage(id) { it.copy(expanded = !it.expanded) }

    fun toggleAttachment(attachment: UploadedAttachment) {
        val id = attachment.fileId
        val current = _state.value
        val expanded = current.expandedAttachments.toMutableSet()
        if (!expanded.add(id)) {
            expanded.remove(id)
            _state.value = current.copy(expandedAttachments = expanded)
            return
        }
        _state.value = current.copy(expandedAttachments = expanded)
        loadAttachmentPreview(attachment)
    }

    fun loadAttachmentPreview(attachment: UploadedAttachment) {
        val id = attachment.fileId
        val current = _state.value
        if (current.attachmentPreviews[id]?.loading == true || current.attachmentPreviews[id]?.text != null || current.attachmentPreviews[id]?.imageBytes != null || current.attachmentPreviews[id]?.pdfBytes != null) return
        _state.value = current.copy(
            attachmentPreviews = current.attachmentPreviews + (id to AttachmentPreview(loading = true)),
        )
        viewModelScope.launch {
            val previewAttachment = attachment.previewUrl?.let { attachment.copy(url = it) } ?: attachment
            runCatching { repository.download(current.token, previewAttachment) }
                .onSuccess { bytes ->
                    val isImage = isImageAttachment(attachment)
                    val isPdf = attachment.previewUrl?.contains("pdf", ignoreCase = true) == true ||
                        attachment.previewMimeType.equals("application/pdf", ignoreCase = true) ||
                        attachment.mimeType.equals("application/pdf", ignoreCase = true) ||
                        attachment.filename.substringAfterLast('.', "").equals("pdf", ignoreCase = true)
                    val extension = attachment.filename.substringAfterLast('.', "").lowercase()
                    val isText = attachment.mimeType.startsWith("text/") ||
                        attachment.mimeType.contains("json") ||
                        extension in setOf("txt", "md", "markdown", "qmd", "csv", "json", "html", "htm", "xml", "log")
                    val text = if (!isImage && isText) bytes.toString(Charsets.UTF_8).take(12000) else null
                    _state.value = _state.value.copy(attachmentPreviews = _state.value.attachmentPreviews + (id to AttachmentPreview(text = text, imageBytes = if (isImage) bytes else null, pdfBytes = if (!isImage && isPdf) bytes else null)))
                }
                .onFailure { failure ->
                    _state.value = _state.value.copy(attachmentPreviews = _state.value.attachmentPreviews + (id to AttachmentPreview(error = friendlyError(failure))))
                }
        }
    }

    fun downloadAttachment(context: Context, attachment: UploadedAttachment, onComplete: (Boolean) -> Unit = {}) {
        val current = _state.value
        viewModelScope.launch {
            val result = runCatching {
                val bytes = repository.download(current.token, attachment.copy(url = attachment.downloadUrl ?: attachment.url))
                withContext(Dispatchers.IO) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        val values = ContentValues().apply {
                            put(MediaStore.Downloads.DISPLAY_NAME, attachment.filename)
                            put(MediaStore.Downloads.MIME_TYPE, attachment.mimeType)
                            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/溯源Agent")
                        }
                        val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                            ?: error("无法创建下载文件")
                        runCatching { context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } }
                            .onFailure { context.contentResolver.delete(uri, null, null) }
                            .getOrThrow()
                    } else {
                        val directory = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                        directory.mkdirs()
                        File(directory, attachment.filename).writeBytes(bytes)
                    }
                }
            }
            onComplete(result.isSuccess)
        }
    }

    fun downloadPreview(context: Context, attachment: UploadedAttachment, bytes: ByteArray, onComplete: (Boolean) -> Unit = {}) {
        val filename = if (attachment.filename.substringAfterLast('.', "").equals("pdf", ignoreCase = true)) {
            attachment.filename
        } else {
            attachment.filename.substringBeforeLast('.', attachment.filename) + ".pdf"
        }
        viewModelScope.launch {
            val result = runCatching {
                withContext(Dispatchers.IO) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        val values = ContentValues().apply {
                            put(MediaStore.Downloads.DISPLAY_NAME, filename)
                            put(MediaStore.Downloads.MIME_TYPE, "application/pdf")
                            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/溯源Agent")
                        }
                        val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                            ?: error("无法创建下载文件")
                        runCatching { context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } }
                            .onFailure { context.contentResolver.delete(uri, null, null) }
                            .getOrThrow()
                    } else {
                        val directory = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                        directory.mkdirs()
                        File(directory, filename).writeBytes(bytes)
                    }
                }
            }
            onComplete(result.isSuccess)
        }
    }

    fun cancel() {
        val current = _state.value
        val session = current.sessionId
        pendingTurns.removeAll { it.sessionId == session }
        // Update the UI before the cancellation request so the stop button
        // responds immediately even if the gateway takes time to acknowledge.
        _state.value = current.copy(loading = false)
        if (session == null) return
        streamJob?.cancel()
        streamJob = null
        viewModelScope.launch {
            runCatching { repository.cancel(current.token, session) }
                .onFailure { if (it is ApiException && it.statusCode == 401) logout("登录已过期，请重新登录") }
        }
    }

    fun steer() {
        val current = _state.value
        val session = current.sessionId
        val message = current.draft.trim()
        if (!current.loading || session.isNullOrBlank() || message.isBlank()) return
        _state.value = current.copy(draft = "", error = null)
        viewModelScope.launch {
            runCatching { repository.steer(current.token, session, message) }
                .onFailure { failure ->
                    if (failure is ApiException && failure.statusCode == 401) logout("登录已过期，请重新登录")
                    else _state.value = _state.value.copy(error = friendlyError(failure))
                }
        }
    }

    fun transcribe(file: File) {
        val current = _state.value
        viewModelScope.launch {
            _state.value = current.copy(loading = true, error = null)
            runCatching { repository.transcribe(current.token, file) }
                .onSuccess { text -> _state.value = _state.value.copy(draft = text, loading = false) }
                .onFailure { failure ->
                    if (failure is ApiException && failure.statusCode == 401) logout("登录已过期，请重新登录")
                    else _state.value = _state.value.copy(loading = false, error = friendlyError(failure))
                }
        }
    }

    fun uploadAttachment(context: Context, uri: Uri) {
        val current = _state.value
        viewModelScope.launch {
            _state.value = _state.value.copy(error = null)
            runCatching {
                val resolver = context.contentResolver
                val filename = resolver.query(uri, null, null, null, null)?.use { cursor ->
                    val index = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                    if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
                } ?: "attachment"
                val mimeType = resolver.getType(uri) ?: "application/octet-stream"
                val file = File(context.cacheDir, "upload-${System.currentTimeMillis()}-${filename.replace(Regex("[^A-Za-z0-9._-]"), "_")}")
                resolver.openInputStream(uri).use { input ->
                    requireNotNull(input) { "无法读取文件" }
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                repository.upload(current.token, file, filename, mimeType)
            }.onSuccess { attachment ->
                _state.value = _state.value.copy(attachments = _state.value.attachments + attachment)
            }.onFailure { failure ->
                if (failure is ApiException && failure.statusCode == 401) logout("登录已过期，请重新登录")
                else _state.value = _state.value.copy(error = friendlyError(failure))
            }
        }
    }

    fun logout(message: String? = null) {
        streamJob?.cancel(); streamJob = null
        store.clear()
        _state.value = AppUiState(error = message)
    }

    private fun refreshSessions() {
        val token = _state.value.token
        if (token.isBlank()) return
        viewModelScope.launch {
            runCatching { repository.sessions(token) }
                .onSuccess { sessions ->
                    val current = _state.value
                    if (sessions.isEmpty()) {
                        _state.value = current.copy(sessions = emptyList(), sessionId = null, loading = false)
                        return@onSuccess
                    }

                    // A newly-created session can be listed before the last
                    // conversation and contain no messages yet. Restore the
                    // newest session with real content so startup never lands
                    // on an empty composer while history is available.
                    if (current.messages.isEmpty()) {
                        _state.value = current.copy(
                            sessions = sessions,
                            sessionId = null,
                            loading = true,
                        )
                        var selectedSession: SessionInfo? = null
                        var restoredMessages: List<ChatMessage> = emptyList()
                        var lastFailure: Throwable? = null
                        for (candidate in sessions) {
                            val result = runCatching { repository.messages(token, candidate.sessionId) }
                            result.onFailure { lastFailure = it }
                            val messages = result.getOrNull().orEmpty()
                            if (messages.isNotEmpty()) {
                                selectedSession = candidate
                                restoredMessages = messages
                                break
                            }
                        }
                        val selected = selectedSession ?: sessions.first()
                        _state.value = _state.value.copy(
                            sessions = sessions,
                            sessionId = selected.sessionId,
                            messages = restoredMessages,
                            loading = false,
                            error = if (selectedSession == null && restoredMessages.isEmpty() && lastFailure != null) friendlyError(lastFailure!!) else null,
                        )
                    } else {
                        _state.value = current.copy(
                            sessions = sessions,
                            sessionId = current.sessionId ?: sessions.first().sessionId,
                            loading = false,
                        )
                    }
                }
                .onFailure { if (it is ApiException && it.statusCode == 401) logout("登录已过期，请重新登录") }
        }
    }

    private fun friendlyError(error: Throwable): String = error.message?.ifBlank { "请求失败，请稍后重试" } ?: "请求失败，请稍后重试"
}
