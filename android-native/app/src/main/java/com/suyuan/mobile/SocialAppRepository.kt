package com.suyuan.mobile

import kotlinx.coroutines.flow.Flow
import java.io.File

class SocialAppRepository(private val api: SocialAppApi) {
    suspend fun login(accountId: String, secret: String) = api.login(accountId, secret)
    suspend fun oidcConfig() = api.oidcConfig()
    suspend fun exchangeOidcCode(code: String, codeVerifier: String, redirectUri: String) =
        api.exchangeOidcCode(code, codeVerifier, redirectUri)
    suspend fun refresh(refreshToken: String) = api.refresh(refreshToken)
    suspend fun registerPushDevice(token: String, deviceId: String) = api.registerPushDevice(token, deviceId)
    suspend fun unregisterPushDevice(token: String, deviceId: String) = api.unregisterPushDevice(token, deviceId)
    fun stream(token: String, query: String, sessionId: String?, attachments: List<UploadedAttachment> = emptyList()): Flow<AgentEvent> = api.stream(token, query, sessionId, attachments)
    suspend fun sessions(token: String, limit: Int = 30, offset: Int = 0) = api.sessions(token, limit, offset)
    suspend fun createSession(token: String) = api.createSession(token)
    suspend fun renameSession(token: String, sessionId: String, title: String) = api.renameSession(token, sessionId, title)
    suspend fun deleteSession(token: String, sessionId: String) = api.deleteSession(token, sessionId)
    suspend fun messages(token: String, sessionId: String) = api.messages(token, sessionId)
    suspend fun broadcasts(token: String, limit: Int = 30, before: String? = null) = api.broadcasts(token, limit, before)
    suspend fun markBroadcastRead(token: String, messageId: String) = api.markBroadcastRead(token, messageId)
    suspend fun markAllBroadcastsRead(token: String) = api.markAllBroadcastsRead(token)
    suspend fun deleteBroadcast(token: String, messageId: String) = api.deleteBroadcast(token, messageId)
    suspend fun cancel(token: String, sessionId: String) = api.cancel(token, sessionId)
    suspend fun steer(token: String, sessionId: String, message: String) = api.steer(token, sessionId, message)
    suspend fun transcribe(token: String, audioFile: File) = api.transcribe(token, audioFile)
    suspend fun upload(token: String, file: File, filename: String, mimeType: String) = api.upload(token, file, filename, mimeType)
    suspend fun deleteUpload(token: String, fileId: String) = api.deleteUpload(token, fileId)
    suspend fun download(token: String, attachment: UploadedAttachment) = api.download(token, attachment)
}
