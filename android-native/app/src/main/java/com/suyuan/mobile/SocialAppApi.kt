package com.suyuan.mobile

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.withContext
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
data class BroadcastInbox(val messages: List<BroadcastMessage>, val unreadCount: Int)
data class ChatMessage(
    val id: String,
    val kind: String,
    val content: String,
    val attachments: List<UploadedAttachment> = emptyList(),
    val streaming: Boolean = false,
    val expanded: Boolean = false,
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
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("file_id", fileId)
        put("name", filename)
        put("filename", filename)
        put("type", fileType)
        put("mime_type", mimeType)
        put("url", url)
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
            )
        }
    }
}

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

    fun stream(token: String, query: String, sessionId: String?, attachments: List<UploadedAttachment> = emptyList()): Flow<AgentEvent> = channelFlow {
        withContext(Dispatchers.IO) {
            val payload = JSONObject().apply {
                put("query", query)
                if (sessionId != null) put("session_id", sessionId)
                put("attachments", org.json.JSONArray().apply { attachments.forEach { put(it.toJson()) } })
            }.toString().toRequestBody("application/json".toMediaType())
            val response = client.newCall(
                Request.Builder().url(url("/api/social/app/chat/stream"))
                    .header("Authorization", "Bearer $token").post(payload).build()
            ).execute()
            response.use {
                if (!it.isSuccessful) throw ApiException(it.code, "请求失败 (${it.code})")
                val source = it.body?.source() ?: error("服务端未返回流")
                source.use { buffered ->
                    var eventData: String? = null
                    while (true) {
                        val line = buffered.readUtf8Line() ?: break
                        when {
                            line.startsWith("data: ") -> eventData = line.removePrefix("data: ")
                            line.isBlank() && eventData != null -> {
                                val json = JSONObject(eventData!!)
                                send(AgentEvent(json.optString("type", "message"), json.opt("data").toString()))
                                eventData = null
                            }
                        }
                    }
                }
            }
        }
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

    suspend fun sessions(token: String): List<SessionInfo> = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/sessions"))
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
                    add(ChatMessage("history-$index", kind, content, attachments, streaming = false, expanded = false))
                }
            }
        }
    }

    suspend fun broadcasts(token: String): BroadcastInbox = withContext(Dispatchers.IO) {
        val response = client.newCall(
            Request.Builder().url(url("/api/social/app/broadcasts"))
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
            BroadcastInbox(messages, json.optInt("unread_count", messages.count { !it.read }))
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
