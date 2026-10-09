package com.suyuan.mobile

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.channels.awaitClose
import java.io.IOException
import java.util.UUID
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

data class LoginResult(
    val token: String,
    val accountId: String,
    val displayName: String,
    val refreshToken: String? = null,
    val expiresAt: Long = 0L,
    val refreshExpiresAt: Long = 0L,
)
data class OidcConfig(
    val authorizationEndpoint: String,
    val clientId: String,
    val redirectUri: String,
    val scopes: String,
)
data class AgentEvent(val type: String, val data: String)
data class SessionInfo(val sessionId: String, val mode: String, val title: String = "新对话", val updatedAt: String? = null)
data class BroadcastMessage(
    val messageId: String,
    val content: String,
    val timestamp: String? = null,
    val read: Boolean = false,
    val attachments: List<UploadedAttachment> = emptyList(),
)
data class BroadcastInbox(
    val messages: List<BroadcastMessage>,
    val unreadCount: Int,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
)
data class ReportResult(
    val reportId: String, val taskId: String, val executionId: String, val taskName: String,
    val reportType: String, val title: String, val summary: String, val generatedAt: String?,
    val read: Boolean, val attachments: List<UploadedAttachment> = emptyList(),
)
data class ReportInbox(val reports: List<ReportResult>, val unreadCount: Int, val nextCursor: String? = null, val hasMore: Boolean = false)
data class ScheduledTask(val taskId: String, val name: String, val taskType: String, val enabled: Boolean = true, val description: String = "", val nextRunAt: String? = null, val totalRuns: Int = 0, val successRuns: Int = 0, val broadcastEnabled: Boolean = false)
data class ChatMessage(
    val id: String,
    val kind: String,
    val content: String,
    val attachments: List<UploadedAttachment> = emptyList(),
    val streaming: Boolean = false,
    val expanded: Boolean = false,
    val durationMs: Long? = null,
    val toolCount: Int = 0,
)

data class AttachmentVariant(
    val format: String,
    val filename: String,
    val mimeType: String,
    val url: String,
)

/** Only expose user-meaningful reasoning in the mobile transcript. */
fun isVisibleThought(text: String): Boolean {
    val value = text.trim()
    if (value.isBlank()) return false
    if (value == "思考中" || value == "思考中..." || value == "思考回复策略") return false
    if (value.startsWith("准备调用工具") || value.startsWith("调用工具") || value.startsWith("执行行动")) return false
    return true
}

data class UploadedAttachment(
    val fileId: String,
    val filename: String,
    val fileType: String,
    val mimeType: String,
    val url: String,
    val previewUrl: String? = null,
    val previewMimeType: String? = null,
    val downloadUrl: String? = null,
    val resourceRef: String?,
    val variants: List<AttachmentVariant> = emptyList(),
    val renderer: String = "",
    val resourceKey: String = "",
    val visualId: String = "",
    val interactive: Boolean = false,
    val groupId: String = "",
    val resourceKind: String = "",
    val resourceRole: String = "",
    val format: String = "",
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("file_id", fileId)
        put("name", filename)
        put("filename", filename)
        put("type", fileType)
        put("mime_type", mimeType)
        put("url", url)
        put("renderer", renderer)
        put("resource_key", resourceKey)
        put("visual_id", visualId)
        put("interactive", interactive)
        put("group_id", groupId)
        put("kind", resourceKind)
        put("role", resourceRole)
        put("format", format)
        previewUrl?.let { put("preview_url", it) }
        previewMimeType?.let { put("preview_mime_type", it) }
        downloadUrl?.let { put("download_url", it) }
        resourceRef?.let { put("resource_ref", JSONObject(it)) }
        if (variants.isNotEmpty()) {
            put("variants", org.json.JSONArray().apply {
                variants.forEach { variant ->
                    put(JSONObject().apply {
                        put("format", variant.format)
                        put("filename", variant.filename)
                        put("name", variant.filename)
                        put("mime_type", variant.mimeType)
                        put("url", variant.url)
                    })
                }
            })
        }
    }

    companion object {
        fun fromJson(item: JSONObject): UploadedAttachment {
            val rawRef = item.opt("resource_ref")
            val ref = rawRef?.let { value ->
                when (value) {
                    is JSONObject -> value.toString()
                    is String -> value
                    else -> null
                }
            }
            val refObject = rawRef as? JSONObject
            val variants = mutableListOf<AttachmentVariant>()
            item.optJSONArray("variants")?.let { array ->
                for (index in 0 until array.length()) {
                    val variant = array.optJSONObject(index) ?: continue
                    val url = variant.optString("url", "")
                    if (url.isBlank()) continue
                    variants += AttachmentVariant(
                        format = variant.optString("format", "file"),
                        filename = variant.optString("filename", variant.optString("name", "附件")),
                        mimeType = variant.optString("mime_type", "application/octet-stream"),
                        url = url,
                    )
                }
            }
            return UploadedAttachment(
                fileId = item.optString("file_id", item.optString("resource_id", refObject?.optString("ref_id", "") ?: "")),
                filename = item.optString("filename", item.optString("name", "附件")),
                fileType = item.optString("file_type", item.optString("type", "document")),
                mimeType = item.optString("mime_type", "application/octet-stream"),
                url = item.optString("url", ""),
                previewUrl = item.optString("preview_url", "").ifBlank { null },
                previewMimeType = item.optString("preview_mime_type", "").ifBlank { null },
                downloadUrl = item.optString("download_url", "").ifBlank { null },
                resourceRef = ref,
                variants = variants,
                renderer = item.optString("renderer", ""),
                resourceKey = item.optString("resource_key", ""),
                visualId = item.optString("visual_id", ""),
                interactive = item.optBoolean("interactive", false),
                groupId = item.optString("group_id", ""),
                resourceKind = item.optString("kind", ""),
                resourceRole = item.optString("role", ""),
                format = item.optString("format", ""),
            )
        }
    }
}

fun isInteractiveChart(attachment: UploadedAttachment): Boolean =
    attachment.renderer == "chart" && attachment.resourceKey == "chart-spec" && attachment.interactive

fun isImageAttachment(attachment: UploadedAttachment): Boolean {
    if (attachment.mimeType.startsWith("image/", ignoreCase = true) || attachment.fileType.equals("image", ignoreCase = true)) return true
    return attachment.filename.substringAfterLast('.', "").lowercase() in setOf("png", "jpg", "jpeg", "gif", "webp", "bmp", "heic", "heif", "avif")
}

class ApiException(val statusCode: Int, message: String) : IllegalStateException(message)

class SocialAppApi(
    private val baseUrl: String = BuildConfig.API_BASE_URL,
    private val sessionStore: AppSessionStore? = null,
) {
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .authenticator(object : okhttp3.Authenticator {
            override fun authenticate(route: okhttp3.Route?, response: okhttp3.Response): Request? {
                if (this@SocialAppApi.responseCount(response) > 1) return null
                val store = this@SocialAppApi.sessionStore ?: return null
                val currentRefresh = store.refreshToken()
                if (currentRefresh.isBlank()) return null
                val refreshed = runCatching { this@SocialAppApi.refreshBlocking(currentRefresh) }.getOrNull() ?: return null
                store.save(refreshed)
                return response.request.newBuilder()
                    .header("Authorization", "Bearer ${refreshed.token}")
                    .build()
            }
        })
        .build()
    private fun url(path: String) = baseUrl.trimEnd('/') + path
    @Volatile private var activeChatCall: okhttp3.Call? = null
    fun reconnectChat() { activeChatCall?.cancel() }
    private fun chatCall(request: Request): okhttp3.Call = client.newCall(request).also { activeChatCall = it }

    private fun responseCount(response: okhttp3.Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count += 1
            prior = prior.priorResponse
        }
        return count
    }

    private fun parseLogin(body: String): LoginResult {
        val json = JSONObject(body)
        return LoginResult(
            token = json.getString("access_token"),
            accountId = json.getString("account_id"),
            displayName = json.optString("display_name", json.getString("account_id")),
            refreshToken = json.optString("refresh_token", "").ifBlank { null },
            expiresAt = json.optLong("expires_at", 0L),
            refreshExpiresAt = json.optLong("refresh_expires_at", 0L),
        )
    }

    private fun refreshBlocking(refreshToken: String): LoginResult {
        val body = JSONObject().put("refresh_token", refreshToken)
            .toString().toRequestBody("application/json".toMediaType())
        val response = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .build()
            .newCall(Request.Builder().url(url("/api/social/app/auth/refresh")).post(body).build())
            .execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "登录已过期")
            return parseLogin(it.body?.string().orEmpty())
        }
    }

    suspend fun login(accountId: String, accountSecret: String): LoginResult = withContext(Dispatchers.IO) {
        val body = JSONObject().apply {
            put("account_id", accountId)
            put("account_secret", accountSecret)
        }.toString().toRequestBody("application/json".toMediaType())
        val response = client.newCall(Request.Builder().url(url("/api/social/app/auth/login")).post(body).build()).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "登录失败 (${it.code})")
            val json = JSONObject(it.body?.string().orEmpty())
            parseLogin(json.toString())
        }
    }

    suspend fun oidcConfig(): OidcConfig = withContext(Dispatchers.IO) {
        val response = client.newCall(Request.Builder().url(url("/api/social/app/auth/oidc/config")).get().build()).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "公司认证配置不可用 (${it.code})")
            val json = JSONObject(it.body?.string().orEmpty())
            OidcConfig(
                authorizationEndpoint = json.getString("authorization_endpoint"),
                clientId = json.getString("client_id"),
                redirectUri = json.getString("redirect_uri"),
                scopes = json.optJSONArray("scopes")?.let { values ->
                    (0 until values.length()).joinToString(" ") { index -> values.getString(index) }
                } ?: "openid profile roles offline_access",
            )
        }
    }

    suspend fun exchangeOidcCode(code: String, codeVerifier: String, redirectUri: String): LoginResult = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("code", code)
            .put("code_verifier", codeVerifier)
            .put("redirect_uri", redirectUri)
            .toString().toRequestBody("application/json".toMediaType())
        val response = client.newCall(Request.Builder().url(url("/api/social/app/auth/oidc/exchange")).post(body).build()).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "公司账号绑定失败 (${it.code})")
            parseLogin(it.body?.string().orEmpty())
        }
    }

    suspend fun refresh(refreshToken: String): LoginResult = withContext(Dispatchers.IO) {
        refreshBlocking(refreshToken)
    }

    suspend fun registerPushDevice(token: String, deviceId: String): Boolean = withContext(Dispatchers.IO) {
        val body = JSONObject().apply {
            put("provider", "getui")
            put("device_id", deviceId)
            put("platform", "android")
            put("app_id", BuildConfig.GETUI_APPID)
        }.toString().toRequestBody("application/json".toMediaType())
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/push/devices"))
                .header("Authorization", "Bearer $token")
                .post(body).build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "推送设备登记失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("registered")
        }
    }

    suspend fun unregisterPushDevice(token: String, deviceId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/push/devices/${java.net.URLEncoder.encode(deviceId, "UTF-8")}"))
                .header("Authorization", "Bearer $token")
                .delete().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "推送设备解绑失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("removed")
        }
    }

    fun stream(token: String, query: String, sessionId: String?, attachments: List<UploadedAttachment> = emptyList(), mode: String = "query", modelTier: String = "auto", requestId: String = UUID.randomUUID().toString()): Flow<AgentEvent> = channelFlow {
        var activeCall: okhttp3.Call? = null
        val worker = launch(Dispatchers.IO) {
            val savedPayload = sessionStore?.pendingTurn()?.let { runCatching { JSONObject(it) }.getOrNull() }
                ?.takeIf { it.optString("request_id") == requestId }
                ?.apply { remove("resume_session_id") }
            val payload = (savedPayload ?: JSONObject().apply {
                put("request_id", requestId)
                put("query", query)
                put("mode", mode)
                put("model_tier", modelTier)
                if (sessionId != null) put("session_id", sessionId)
                put("attachments", org.json.JSONArray().apply { attachments.forEach { put(it.toJson()) } })
            }).toString()
            sessionStore?.savePendingTurn(payload)
            var runId: String? = null
            var sequence = 0L
            var finished = false
            try {
                while (!finished) {
                    try {
                        val authToken = sessionStore?.token()?.ifBlank { token } ?: token
                        if (runId == null) {
                            activeCall = chatCall(Request.Builder().url(url("/api/social/app/chat/runs"))
                                .header("Authorization", "Bearer $authToken")
                                .post(payload.toRequestBody("application/json".toMediaType())).build())
                            activeCall!!.timeout().timeout(30, TimeUnit.SECONDS)
                            activeCall!!.execute().use { response ->
                                if (response.code >= 500) throw IOException("服务暂时不可用")
                                if (!response.isSuccessful) throw ApiException(response.code, "提交对话失败 (${response.code})")
                                val run = JSONObject(response.body?.string().orEmpty())
                                runId = run.getString("run_id")
                                // Keep the original request payload for idempotent retries.
                                sessionStore?.savePendingTurn(JSONObject(payload).put("resume_session_id", run.getString("session_id")).toString())
                            }
                        }
                        activeCall = chatCall(Request.Builder().url(url("/api/social/app/chat/runs/$runId/events?after=$sequence"))
                            .header("Authorization", "Bearer $authToken").build())
                        activeCall!!.execute().use { response ->
                            if (response.code >= 500) throw IOException("服务暂时不可用")
                            if (!response.isSuccessful) throw ApiException(response.code, "恢复对话失败 (${response.code})")
                            val source = response.body?.source() ?: throw IOException("服务端未返回流")
                            var eventData: String? = null
                            var eventSequence = sequence
                            while (!finished) {
                                val line = source.readUtf8Line() ?: break
                                when {
                                    line.startsWith("id: ") -> eventSequence = line.removePrefix("id: ").toLongOrNull() ?: sequence
                                    line.startsWith("data: ") -> eventData = line.removePrefix("data: ")
                                    line.isBlank() && eventData != null -> {
                                        val json = JSONObject(eventData!!)
                                        val type = json.optString("type", "message")
                                        send(AgentEvent(type, json.opt("data").toString()))
                                        sequence = eventSequence
                                        eventData = null
                                        finished = type in setOf("complete", "fatal_error", "incomplete", "interrupted")
                                    }
                                }
                            }
                        }
                        if (!finished) delay(1500)
                    } catch (failure: IOException) {
                        send(AgentEvent("reconnecting", "{}"))
                        delay(2000)
                    }
                }
                sessionStore?.clearPendingTurn(requestId)
                channel.close()
            } catch (failure: Throwable) {
                channel.close(failure)
            }
        }
        awaitClose { activeCall?.cancel(); worker.cancel() }
    }

    suspend fun transcribe(token: String, audioFile: File): String = withContext(Dispatchers.IO) {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("language", "zh")
            .addFormDataPart("file", audioFile.name, audioFile.asRequestBody("audio/mp4".toMediaType()))
            .build()
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/voice/transcribe"))
                .header("Authorization", "Bearer $token").post(body).build()
        ).execute()
        response.use {
            val responseText = it.body?.string().orEmpty()
            if (!it.isSuccessful) {
                val detail = runCatching { JSONObject(responseText).optString("detail") }
                    .getOrNull()
                    ?.takeIf { value -> value.isNotBlank() }
                throw ApiException(it.code, detail ?: "语音识别失败 (${it.code})")
            }
            JSONObject(responseText).getString("text")
        }
    }

    suspend fun upload(token: String, file: File, filename: String, mimeType: String): UploadedAttachment = withContext(Dispatchers.IO) {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("file", filename, file.asRequestBody(mimeType.toMediaType()))
            .build()
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/upload"))
                .header("Authorization", "Bearer $token").post(body).build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "文件上传失败 (${it.code})")
            val json = JSONObject(it.body?.string().orEmpty())
            UploadedAttachment(
                fileId = json.getString("file_id"),
                filename = json.getString("filename"),
                fileType = json.optString("file_type", "file"),
                mimeType = json.optString("mime_type", mimeType),
                url = json.getString("url"),
                previewUrl = json.optString("preview_url", "").ifBlank { null },
                previewMimeType = json.optString("preview_mime_type", "").ifBlank { null },
                downloadUrl = json.optString("download_url", "").ifBlank { null },
                resourceRef = json.optJSONObject("resource_ref")?.toString(),
            )
        }
    }

    suspend fun deleteUpload(token: String, fileId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/upload/${java.net.URLEncoder.encode(fileId, "UTF-8")}"))
                .header("Authorization", "Bearer $token").delete().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "附件删除失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("deleted", true)
        }
    }

    suspend fun sessions(token: String, limit: Int = 30, offset: Int = 0): List<SessionInfo> = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions?limit=$limit&offset=$offset"))
                .header("Authorization", "Bearer $token").get().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "会话查询失败 (${it.code})")
            val array = org.json.JSONArray(it.body?.string().orEmpty())
            buildList {
                for (index in 0 until array.length()) {
                    val item = array.getJSONObject(index)
                    add(SessionInfo(item.getString("session_id"), item.optString("mode", "social"), item.optString("title", "新对话"), if (item.has("updated_at")) item.optString("updated_at") else null))
                }
            }
        }
    }

    suspend fun createSession(token: String): SessionInfo = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions"))
                .header("Authorization", "Bearer $token").post("".toRequestBody("application/json".toMediaType())).build()
        ) .execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "新建对话失败 (${it.code})")
            val json = JSONObject(it.body?.string().orEmpty())
            SessionInfo(json.getString("session_id"), json.optString("mode", "social"), json.optString("title", "新对话"))
        }
    }

    suspend fun renameSession(token: String, sessionId: String, title: String): SessionInfo = withContext(Dispatchers.IO) {
        val body = JSONObject().put("title", title).toString().toRequestBody("application/json".toMediaType())
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions/$sessionId"))
                .header("Authorization", "Bearer $token").patch(body).build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "会话重命名失败 (${it.code})")
            val json = JSONObject(it.body?.string().orEmpty())
            SessionInfo(sessionId, "social", json.optString("title", title))
        }
    }

    suspend fun deleteSession(token: String, sessionId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions/$sessionId"))
                .header("Authorization", "Bearer $token").delete().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "会话删除失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("deleted")
        }
    }

    suspend fun messages(token: String, sessionId: String): List<ChatMessage> = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions/$sessionId/messages"))
                .header("Authorization", "Bearer $token").get().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "历史会话加载失败 (${it.code})")
            val array = JSONObject(it.body?.string().orEmpty()).optJSONArray("messages") ?: org.json.JSONArray()
            buildList {
                for (index in 0 until array.length()) {
                    val item = array.optJSONObject(index) ?: continue
                    val content = item.optString("content").ifBlank { item.optString("text") }
                    val role = item.optString("role").ifBlank { item.optString("type") }
                    val attachments = item.optJSONArray("attachments")?.let { values ->
                        buildList {
                            for (attachmentIndex in 0 until values.length()) {
                                values.optJSONObject(attachmentIndex)?.let { add(UploadedAttachment.fromJson(it)) }
                            }
                        }
                    }.orEmpty()
                    if (content.isBlank() && attachments.isEmpty()) continue
                    val kind = when (role.lowercase()) {
                        "user" -> "user"
                        "thought", "thinking" -> "thought"
                        "tool_use", "tool_result", "process" -> "tool"
                        "fatal_error", "incomplete", "interrupted", "error" -> "error"
                        else -> "assistant"
                    }
                    // Mobile only exposes actual reasoning text. Tool execution details
                    // stay available to the web client but are omitted here.
                    if (kind == "tool") continue
                    if (kind == "thought" && !isVisibleThought(content)) continue
                    add(ChatMessage(item.optString("id", "history-$index"), kind, content, attachments, streaming = false, expanded = false))
                }
            }
        }
    }

    suspend fun broadcasts(token: String, limit: Int = 30, before: String? = null): BroadcastInbox = withContext(Dispatchers.IO) {
        val cursor = before?.let { "&before=${java.net.URLEncoder.encode(it, "UTF-8")}" }.orEmpty()
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/broadcasts?limit=$limit$cursor"))
                .header("Authorization", "Bearer $token").get().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "广播消息查询失败 (${it.code})")
            val json = JSONObject(it.body?.string().orEmpty())
            val array = json.optJSONArray("messages") ?: org.json.JSONArray()
            val messages = buildList {
                for (index in 0 until array.length()) {
                    val item = array.optJSONObject(index) ?: continue
                    val attachments = item.optJSONArray("attachments")?.let { values ->
                        buildList {
                            for (attachmentIndex in 0 until values.length()) {
                                values.optJSONObject(attachmentIndex)?.let { add(UploadedAttachment.fromJson(it)) }
                            }
                        }
                    }.orEmpty()
                    add(
                        BroadcastMessage(
                            messageId = item.optString("message_id", "broadcast-$index"),
                            content = item.optString("content"),
                            timestamp = item.optString("timestamp", "").ifBlank { null },
                            read = item.optBoolean("read", false),
                            attachments = attachments,
                        )
                    )
                }
            }
            BroadcastInbox(
                messages = messages,
                unreadCount = json.optInt("unread_count", messages.count { !it.read }),
                nextCursor = json.optString("next_cursor", "").ifBlank { null },
                hasMore = json.optBoolean("has_more", false),
            )
        }
    }

    suspend fun markBroadcastRead(token: String, messageId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/broadcasts/${java.net.URLEncoder.encode(messageId, "UTF-8")}/read"))
                .header("Authorization", "Bearer $token")
                .post("".toRequestBody("application/json".toMediaType())).build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "广播消息已读失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("read", true)
        }
    }

    suspend fun markAllBroadcastsRead(token: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/broadcasts/read-all"))
                .header("Authorization", "Bearer $token")
                .post("".toRequestBody("application/json".toMediaType())).build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "广播消息已读失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("read_all", true)
        }
    }

    suspend fun deleteBroadcast(token: String, messageId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/broadcasts/${java.net.URLEncoder.encode(messageId, "UTF-8")}"))
                .header("Authorization", "Bearer $token")
                .delete().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "广播消息删除失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("deleted", true)
        }
    }

    suspend fun taskResults(token: String, taskId: String, page: Int, start: String, end: String, station: String, pollutant: String): JSONObject = withContext(Dispatchers.IO) {
        val params = linkedMapOf("task_id" to taskId, "page" to page.toString(), "page_size" to "10")
        if (start.isNotBlank()) params["start"] = "${start}T00:00:00"
        if (end.isNotBlank()) params["end"] = "${end}T23:59:59"
        if (station.isNotBlank()) params["station_id"] = station
        if (pollutant.isNotBlank()) params["pollutant"] = pollutant
        taskQuery(token, "results", params)
    }

    suspend fun taskFacets(token: String, taskId: String): JSONObject = withContext(Dispatchers.IO) {
        taskQuery(token, "facets", mapOf("task_id" to taskId))
    }

    suspend fun reportDownloadFormats(token: String, executionId: String): List<UploadedAttachment> = withContext(Dispatchers.IO) {
        val id = java.net.URLEncoder.encode(executionId, "UTF-8")
        client.newCall(Request.Builder().url(url("/api/social/app/scheduled-tasks/results/$id/report/formats"))
            .header("Authorization", "Bearer $token").get().build()).execute().use { response ->
            if (!response.isSuccessful) throw ApiException(response.code, "报告下载格式加载失败 (${response.code})")
            val formats = JSONObject(response.body?.string().orEmpty()).optJSONArray("formats") ?: org.json.JSONArray()
            buildList {
                for (i in 0 until formats.length()) {
                    val item = formats.optJSONObject(i) ?: continue
                    val format = item.optString("format")
                    val path = item.optString("url")
                    if (format !in setOf("docx", "html") || path.isBlank()) continue
                    add(UploadedAttachment(fileId = "$executionId:$format", filename = item.optString("filename", "report.$format"),
                        fileType = "document", mimeType = if (format == "docx") "application/vnd.openxmlformats-officedocument.wordprocessingml.document" else "text/html",
                        url = path, downloadUrl = path, resourceRef = null, format = format))
                }
            }
        }
    }

    private fun taskQuery(token: String, endpoint: String, params: Map<String, String>): JSONObject {
        val query = params.entries.joinToString("&") { "${it.key}=${java.net.URLEncoder.encode(it.value, "UTF-8")}" }
        client.newCall(Request.Builder().url(url("/api/social/app/scheduled-tasks/$endpoint?$query")).header("Authorization", "Bearer $token").get().build()).execute().use {
            if (!it.isSuccessful) throw ApiException(it.code, "任务数据查询失败 (${it.code})")
            return JSONObject(it.body?.string().orEmpty())
        }
    }

    suspend fun scheduledTasks(token: String): List<ScheduledTask> = withContext(Dispatchers.IO) {
        val response = client.newCall(Request.Builder().url(url("/api/social/app/scheduled-tasks")).header("Authorization", "Bearer $token").get().build()).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "定时任务加载失败 (${it.code})")
            val array = org.json.JSONArray(it.body?.string().orEmpty())
            buildList { for (i in 0 until array.length()) { val item = array.optJSONObject(i) ?: continue; val task = item.optJSONObject("task") ?: item; add(ScheduledTask(task.optString("task_id", task.optString("id")), task.optJSONObject("workspace_entry")?.optString("title")?.takeIf { it.isNotBlank() } ?: task.optString("name", "未命名任务"), task.optString("trigger_type", "scheduled"), task.optBoolean("enabled", true), task.optString("description"), item.optString("next_run_time").ifBlank { task.optString("next_run_at").ifBlank { null } }, task.optInt("total_runs"), task.optInt("success_runs"), task.optBoolean("broadcast_enabled"))) } }
        }
    }

    suspend fun reports(token: String, reportType: String? = null, limit: Int = 30, before: String? = null): ReportInbox = withContext(Dispatchers.IO) {
        val params = buildString { append("?limit=").append(limit); reportType?.takeIf { it.isNotBlank() }?.let { append("&report_type=").append(java.net.URLEncoder.encode(it, "UTF-8")) }; before?.let { append("&before=").append(java.net.URLEncoder.encode(it, "UTF-8")) } }
        val response = client.newCall(Request.Builder().url(url("/api/social/app/report-results$params")).header("Authorization", "Bearer $token").get().build()).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "报告成果查询失败 (${it.code})")
            val json = JSONObject(it.body?.string().orEmpty()); val array = json.optJSONArray("reports") ?: org.json.JSONArray()
            val reports = buildList {
                for (index in 0 until array.length()) { val item = array.optJSONObject(index) ?: continue
                    val attachments = buildList { item.optJSONArray("attachments")?.let { values -> for (i in 0 until values.length()) values.optJSONObject(i)?.let { add(UploadedAttachment.fromJson(it)) } } }
                    add(ReportResult(item.optString("report_id", "report-$index"), item.optString("task_id"), item.optString("execution_id"), item.optString("task_name"), item.optString("report_type"), item.optString("title"), item.optString("summary"), item.optString("generated_at").ifBlank { null }, item.optBoolean("read"), attachments))
                }
            }
            ReportInbox(reports, json.optInt("unread_count", reports.count { !it.read }), json.optString("next_cursor").ifBlank { null }, json.optBoolean("has_more"))
        }
    }

    suspend fun markReportRead(token: String, reportId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(Request.Builder().url(url("/api/social/app/report-results/${java.net.URLEncoder.encode(reportId, "UTF-8")}/read")).header("Authorization", "Bearer $token").post("".toRequestBody("application/json".toMediaType())).build()).execute()
        response.use { if (!it.isSuccessful) throw ApiException(it.code, "报告成果已读失败 (${it.code})"); JSONObject(it.body?.string().orEmpty()).optBoolean("read", true) }
    }

    suspend fun deleteReport(token: String, reportId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(Request.Builder().url(url("/api/social/app/report-results/${java.net.URLEncoder.encode(reportId, "UTF-8")}")).header("Authorization", "Bearer $token").delete().build()).execute()
        response.use { if (!it.isSuccessful) throw ApiException(it.code, "报告成果删除失败 (${it.code})"); JSONObject(it.body?.string().orEmpty()).optBoolean("deleted", true) }
    }

    suspend fun download(token: String, attachment: UploadedAttachment): ByteArray = withContext(Dispatchers.IO) {
        val path = attachment.url.ifBlank { "/api/upload/${attachment.fileId}" }
        val response = client.newCall(
            Request.Builder().url(if (path.startsWith("http")) path else url(path))
                .header("Authorization", "Bearer $token").get().build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "附件读取失败 (${it.code})")
            it.body?.bytes() ?: ByteArray(0)
        }
    }

    suspend fun cancel(token: String, sessionId: String): Boolean = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions/$sessionId/cancel"))
                .header("Authorization", "Bearer $token").post("".toRequestBody()).build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "取消失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("cancelled")
        }
    }

    suspend fun steer(token: String, sessionId: String, message: String): Boolean = withContext(Dispatchers.IO) {
        val body = JSONObject().put("message", message).toString().toRequestBody("application/json".toMediaType())
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions/$sessionId/steer"))
                .header("Authorization", "Bearer $token").post(body).build()
        ).execute()
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, "插话失败 (${it.code})")
            JSONObject(it.body?.string().orEmpty()).optBoolean("accepted")
        }
    }
}
