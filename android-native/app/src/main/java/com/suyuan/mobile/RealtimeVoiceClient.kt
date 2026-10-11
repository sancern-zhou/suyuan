package com.suyuan.mobile

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.ArrayDeque
import java.util.concurrent.TimeUnit

/** Streams microphone PCM to the authenticated backend ASR proxy. */
class RealtimeVoiceClient(
    private val baseUrl: String,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var socket: WebSocket? = null
    private var recorder: AudioRecord? = null
    @Volatile private var sending = false
    @Volatile private var generation = 0L
    @Volatile private var finishing = false
    @Volatile private var finishGeneration = 0L
    private var finishCallback: (() -> Unit)? = null

    // Audio captured before the backend ASR task is live is buffered here and
    // flushed on "ready", so words spoken during the websocket handshake are
    // recognized instead of lost.
    private val bufferLock = Any()
    private val pendingChunks = ArrayDeque<ByteString>()
    private var pendingBytes = 0
    private var readyToSend = false
    private var stopSent = false

    fun start(
        token: String,
        onReady: () -> Unit,
        onText: (String, Boolean) -> Unit,
        onError: (String) -> Unit,
    ) {
        stop()
        val runId = synchronized(this) {
            generation += 1
            generation
        }
        synchronized(bufferLock) {
            pendingChunks.clear()
            pendingBytes = 0
            readyToSend = false
            stopSent = false
        }
        val endpoint = baseUrl.trimEnd('/')
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://") + "/api/social/app/voice/realtime"
        val request = Request.Builder()
            .url(endpoint)
            .header("Authorization", "Bearer $token")
            .build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                if (!isCurrent(runId)) return
                runCatching {
                    val json = JSONObject(text)
                    when (json.optString("type")) {
                        "ready" -> {
                            synchronized(bufferLock) {
                                if (isCurrent(runId)) {
                                    readyToSend = true
                                    drainPendingLocked(webSocket)
                                    if (finishing && finishGeneration == runId) sendStopLocked()
                                }
                            }
                            if (isCurrent(runId)) onReady()
                            Unit
                        }
                        "partial" -> {
                            if (isCurrent(runId)) onText(json.optString("text"), false) else Unit
                            Unit
                        }
                        "final" -> {
                            if (isCurrent(runId)) onText(json.optString("text"), true) else Unit
                            Unit
                        }
                        "finished" -> {
                            stopRecorder()
                            if (isCurrent(runId) && finishing && finishGeneration == runId) {
                                val callback = finishCallback
                                finishCallback = null
                                finishing = false
                                callback?.invoke()
                            }
                            if (isCurrent(runId)) synchronized(this@RealtimeVoiceClient) { generation += 1 }
                            webSocket.close(1000, "voice finished")
                        }
                        "error" -> {
                            if (isCurrent(runId)) onError(json.optString("message", "实时语音识别失败")) else Unit
                            Unit
                        }
                        else -> Unit
                    }
                }.onFailure { if (isCurrent(runId)) onError("语音识别响应异常") }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                if (!isCurrent(runId)) return
                stopRecorder()
                val callback = if (finishing && finishGeneration == runId) finishCallback else null
                finishCallback = null
                finishing = false
                callback?.invoke()
                onError("实时语音识别连接失败，请检查后端网络")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (isCurrent(runId)) {
                    stopRecorder()
                    val callback = if (finishing && finishGeneration == runId) finishCallback else null
                    finishCallback = null
                    finishing = false
                    callback?.invoke()
                    synchronized(this@RealtimeVoiceClient) { generation += 1 }
                }
            }
        })
        startRecorder(runId, onError)
    }

    fun stop() {
        synchronized(this) {
            generation += 1
            finishing = false
            finishGeneration = 0L
            finishCallback = null
        }
        sending = false
        stopRecorder()
        socket?.send("{\"type\":\"stop\"}")
        socket = null
        synchronized(bufferLock) {
            readyToSend = false
            stopSent = false
            pendingChunks.clear()
            pendingBytes = 0
        }
    }

    /** Finish a live recognition session and invoke the callback after the final result. */
    fun finish(onFinished: () -> Unit) {
        val runId = generation
        if (runId == 0L || socket == null) {
            onFinished()
            return
        }
        finishGeneration = runId
        finishCallback = onFinished
        finishing = true
        sending = false
        stopRecorder()
        synchronized(bufferLock) {
            if (readyToSend) sendStopLocked()
        }
        // Released before "ready": the ready handler flushes the buffered
        // audio first and only then sends stop, so nothing is dropped.
    }

    private fun isCurrent(runId: Long): Boolean = generation == runId

    private fun startRecorder(runId: Long, onError: (String) -> Unit) {
        if (!isCurrent(runId)) return
        if (sending) return
        sending = true
        Thread {
            var audioRecord: AudioRecord? = null
            try {
                val minBuffer = AudioRecord.getMinBufferSize(
                    16000,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                )
                if (minBuffer <= 0) {
                    onError("手机不支持 16kHz 录音")
                    return@Thread
                }
                val bufferSize = maxOf(minBuffer, 6400)
                val record = try {
                    AudioRecord(
                        MediaRecorder.AudioSource.MIC,
                        16000,
                        AudioFormat.CHANNEL_IN_MONO,
                        AudioFormat.ENCODING_PCM_16BIT,
                        bufferSize,
                    )
                } catch (_: Throwable) {
                    onError("无法打开麦克风，请检查权限")
                    return@Thread
                }
                audioRecord = record
                recorder = record
                if (!sending || !isCurrent(runId)) return@Thread
                record.startRecording()
                val buffer = ByteArray(3200)
                while (sending && isCurrent(runId)) {
                    val count = record.read(buffer, 0, buffer.size)
                    if (count > 0 && isCurrent(runId)) emitChunk(runId, buffer, count)
                }
            } catch (_: Throwable) {
                if (sending && isCurrent(runId)) onError("麦克风采集失败")
            } finally {
                audioRecord?.let {
                    runCatching { it.stop() }
                    it.release()
                    if (recorder === it) recorder = null
                }
            }
        }.start()
    }

    private fun stopRecorder() {
        sending = false
        recorder?.let { runCatching { it.stop() } }
        recorder = null
    }

    /** Send one PCM chunk, or park it in the buffer while the ASR task starts. */
    private fun emitChunk(runId: Long, chunk: ByteArray, count: Int) {
        val payload = chunk.toByteString(0, count)
        synchronized(bufferLock) {
            if (!isCurrent(runId)) return
            if (!readyToSend) {
                pendingChunks.addLast(payload)
                pendingBytes += payload.size
                while (pendingBytes > MAX_PENDING_BYTES && pendingChunks.isNotEmpty()) {
                    pendingBytes -= pendingChunks.removeFirst().size
                }
                return
            }
            socket?.send(payload)
        }
    }

    private fun drainPendingLocked(target: WebSocket) {
        while (pendingChunks.isNotEmpty()) {
            target.send(pendingChunks.removeFirst())
        }
        pendingBytes = 0
    }

    private fun sendStopLocked() {
        if (stopSent) return
        stopSent = true
        socket?.send("{\"type\":\"stop\"}")
    }

    private companion object {
        /** ~60s of 16kHz mono 16-bit PCM; caps memory if the handshake stalls. */
        const val MAX_PENDING_BYTES = 1_920_000
    }
}
