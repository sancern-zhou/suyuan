package com.suyuan.mobile

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.toList
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatReconnectTest {
    @Test fun reconnectUsesCursorAndDoesNotResubmit() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"run_id":"run1","session_id":"session1","status":"running"}"""))
            server.enqueue(MockResponse().setBody("id: 1\ndata: {\"type\":\"start\",\"data\":{\"session_id\":\"session1\"}}\n\nid: 2\ndata: {\"type\":\"streaming_text\",\"data\":{\"chunk\":\"hello\"}}\n\n"))
            server.enqueue(MockResponse().setBody("id: 3\ndata: {\"type\":\"complete\",\"data\":{\"answer\":\"hello world\"}}\n\n"))
            val events = SocialAppApi(server.url("/").toString()).stream("token", "question", "session1", requestId = "request1").toList()
            assertEquals(listOf("start", "streaming_text", "complete"), events.map { it.type })
            val submit = server.takeRequest()
            assertEquals("POST", submit.method)
            assertEquals("request1", JSONObject(submit.body.readUtf8()).getString("request_id"))
            assertEquals("/api/social/app/chat/runs/run1/events?after=0", server.takeRequest().path)
            assertEquals("/api/social/app/chat/runs/run1/events?after=2", server.takeRequest().path)
            assertEquals(3, server.requestCount)
        } finally { server.shutdown() }
    }

    @Test fun lostSubmitAcknowledgementRetriesSameRequestId() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
            server.enqueue(MockResponse().setBody("""{"run_id":"run1","session_id":"session1","status":"completed"}"""))
            server.enqueue(MockResponse().setBody("id: 1\ndata: {\"type\":\"complete\",\"data\":{\"answer\":\"done\"}}\n\n"))
            val events = SocialAppApi(server.url("/").toString()).stream("token", "question", null, requestId = "same-request").toList()
            assertEquals("complete", events.last().type)
            val first = server.takeRequest()
            val retry = server.takeRequest()
            assertEquals("POST", retry.method)
            assertEquals(first.body.readUtf8(), retry.body.readUtf8())
        } finally { server.shutdown() }
    }
}
