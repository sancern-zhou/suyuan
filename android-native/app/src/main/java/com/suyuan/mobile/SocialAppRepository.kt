package com.suyuan.mobile

import kotlinx.coroutines.flow.Flow
import java.io.File

class SocialAppRepository(private val api: SocialAppApi) {
    suspend fun login(accountId: String, secret: String) = api.login(accountId, secret)
    fun stream(token: String, query: String, sessionId: String?, attachments: List<UploadedAttachment> = emptyList()): Flow<AgentEvent> = api.stream(token, query, sessionId, attachments)
    suspend fun sessions(token: String) = api.sessions(token)
    suspend fun createSession(token: String) = api.createSession(token)
    suspend fun renameSession(token: String, sessionId: String, title: String) = api.renameSession(token, sessionId, title)
    suspend fun deleteSession(token: String, sessionId: String) = api.deleteSession(token, sessionId)
    suspend fun messages(token: String, sessionId: String) = api.messages(token, sessionId)
    suspend fun cancel(token: String, sessionId: String) = api.cancel(token, sessionId)
    suspend fun steer(token: String, sessionId: String, message: String) = api.steer(token, sessionId, message)
    suspend fun transcribe(token: String, audioFile: File) = api.transcribe(token, audioFile)
    suspend fun upload(token: String, file: File, filename: String, mimeType: String) = api.upload(token, file, filename, mimeType)
    suspend fun download(token: String, attachment: UploadedAttachment) = api.download(token, attachment)
}
