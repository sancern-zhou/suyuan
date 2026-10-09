package com.suyuan.mobile

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AgentQuestionsTest {
    private val question = AgentQuestion("选择格式", "格式", listOf(
        AgentQuestionOption("HTML", "手机浏览"), AgentQuestionOption("PDF", "固定版式")), false)

    @Test fun singleChoiceAndCustomAreExclusive() {
        val custom = AgentQuestionAnswer().select(0, false).selectCustom(false)
        assertTrue(custom.selected.isEmpty())
        assertFalse(custom.valid(question))
        assertTrue(custom.copy(custom = "文档").valid(question))
        val selected = custom.copy(custom = "文档").select(1, false)
        assertFalse(selected.customEnabled)
        assertTrue(selected.valid(question))
        assertFalse(AgentQuestionAnswer(selected = setOf(0, 1)).valid(question))
        assertFalse(AgentQuestionAnswer(selected = setOf(2)).valid(question))
    }

    @Test fun multipleChoicesPreserveCustomAndSerializeStably() {
        val multiple = question.copy(multiSelect = true)
        val answer = AgentQuestionAnswer().select(1, true).select(0, true)
            .selectCustom(true).copy(custom = "  DOCX  ")
        assertTrue(answer.valid(multiple))
        assertEquals("[0,1]", answer.toJson().getJSONArray("selected").toString())
        assertEquals("DOCX", answer.toJson().getString("custom"))
        assertEquals(setOf(0), answer.select(1, true).selected)
    }

    @Test fun restoredQuestionAndReplyHideProtocolDetails() {
        val json = JSONObject("""{"kind":"structured_question","interaction_id":"q1","session_id":"s1","questions":[{"header":"格式","question":"选择格式","options":[{"label":"HTML","description":"手机","preview":null},{"label":"PDF","description":"固定"}]}]}""")
        val interaction = AgentQuestionInteraction.fromJson(json)
        assertEquals("", interaction.questions.first().options.first().preview)
        assertEquals(interaction, AgentQuestionInteraction.fromJson(interaction.toJson()))
        assertEquals("选择格式：HTML、图表", questionReplyDisplay("【结构化提问回复】继续任务：\n- 选择格式：[\"HTML\", \"图表\"]"))
        assertEquals("普通问题", questionReplyDisplay("普通问题"))
    }

    @Test fun oldBackendQuestionWithoutIdIsRejectedClearly() {
        val oldEvent = JSONObject("""{"kind":"structured_question","session_id":"s1","questions":[{"header":"格式","question":"选择格式","options":[{"label":"HTML","description":"手机"},{"label":"PDF","description":"固定"}]}]}""")
        val failure = runCatching { AgentQuestionInteraction.fromJson(oldEvent) }.exceptionOrNull()
        assertTrue(failure is IllegalArgumentException)
        assertEquals("提问事件缺少必要信息", failure?.message)
    }

    @Test fun questionEndpointsUseAppAuthenticationAndCorrectAnswerShape() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"interaction":null}"""))
            server.enqueue(MockResponse().setBody("""{"status":"resolved","request_id":"answer:q1"}"""))
            val api = SocialAppApi(server.url("/").toString())
            assertNull(api.pendingInteraction("token", "s1"))
            api.resolveInteraction("token", "s1", "q1", "answer", listOf(AgentQuestionAnswer(selected = setOf(1))))
            assertEquals("/api/social/app/sessions/s1/interaction", server.takeRequest().path)
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("Bearer token", request.getHeader("Authorization"))
            assertEquals("/api/social/app/sessions/s1/interactions/q1", request.path)
            val answer = JSONObject(request.body.readUtf8()).getJSONArray("answers").getJSONObject(0)
            assertEquals(1, answer.getJSONArray("selected").getInt(0))
            assertTrue(answer.isNull("custom"))
        } finally { server.shutdown() }
    }
}
