package com.suyuan.mobile

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
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
    private var finishGeneration = 0L
    private var finishCallback: (() -> Unit)? = null

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
                            if (isCurrent(runId)) {
                                onReady()
                                if (isCurrent(runId) && !finishing) startRecorder(webSocket, onError, runId) else Unit
                            }
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
        socket?.send("{\"type\":\"stop\"}")
    }

    private fun isCurrent(runId: Long): Boolean = generation == runId

    private fun startRecorder(webSocket: WebSocket, onError: (String) -> Unit, runId: Long) {
        if (!isCurrent(runId)) return
        if (sending) return
        val minBuffer = AudioRecord.getMinBufferSize(
            16000,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuffer <= 0) {
            onError("手机不支持 16kHz 录音")
            return
        }
        val bufferSize = maxOf(minBuffer, 6400)
        val audioRecord = runCatching {
            AudioRecord(
                MediaRecorder.AudioSource.MIC,
                16000,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize,
            )
        }.getOrElse {
            onError("无法打开麦克风，请检查权限")
            return
        }
        recorder = audioRecord
        sending = true
        Thread {
            val buffer = ByteArray(3200)
            try {
                audioRecord.startRecording()
                while (sending && isCurrent(runId)) {
                    val count = audioRecord.read(buffer, 0, buffer.size)
                    if (count > 0 && isCurrent(runId)) webSocket.send(buffer.toByteString(0, count))
                }
            } catch (_: Throwable) {
                if (sending && isCurrent(runId)) onError("麦克风采集失败")
            } finally {
                runCatching { audioRecord.stop() }
                audioRecord.release()
                if (recorder === audioRecord) recorder = null
            }
        }.start()
    }

    private fun stopRecorder() {
        sending = false
        recorder?.let { runCatching { it.stop() } }
        recorder = null
    }
}
