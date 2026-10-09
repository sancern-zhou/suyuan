package com.suyuan.mobile

import org.json.JSONArray
import org.json.JSONObject

data class AgentQuestionOption(val label: String, val description: String, val preview: String = "")
data class AgentQuestion(val question: String, val header: String, val options: List<AgentQuestionOption>, val multiSelect: Boolean)
data class AgentQuestionAnswer(val selected: Set<Int> = emptySet(), val customEnabled: Boolean = false, val custom: String = "") {
    fun select(index: Int, multiple: Boolean): AgentQuestionAnswer = if (multiple) {
        copy(selected = if (index in selected) selected - index else selected + index)
    } else copy(selected = setOf(index), customEnabled = false, custom = "")
    fun selectCustom(multiple: Boolean): AgentQuestionAnswer = copy(
        selected = if (multiple) selected else emptySet(), customEnabled = !customEnabled,
    )
    fun valid(question: AgentQuestion): Boolean {
        val customCount = if (customEnabled && custom.trim().isNotBlank()) 1 else 0
        if (customEnabled && custom.trim().isBlank()) return false
        if (selected.any { it !in question.options.indices }) return false
        return if (question.multiSelect) selected.size + customCount > 0 else selected.size + customCount == 1
    }
    fun toJson(): JSONObject = JSONObject().put("selected", JSONArray(selected.sorted()))
        .put("custom", if (customEnabled) custom.trim() else JSONObject.NULL)
}

/** Hide the continuation instruction from the user-facing history. */
fun questionReplyDisplay(query: String): String {
    if (!query.startsWith("【结构化提问回复】")) return query
    return runCatching {
        query.lineSequence().drop(1).map { line ->
            val split = line.indexOf("：[\"")
            require(split >= 0)
            val labels = JSONArray(line.substring(split + 1))
            line.substring(0, split).removePrefix("- ") + "：" +
                (0 until labels.length()).joinToString("、") { labels.getString(it) }
        }.joinToString("\n")
    }.getOrDefault("已提交问题回答")
}

data class AgentQuestionInteraction(val interactionId: String, val sessionId: String, val title: String, val mode: String, val questions: List<AgentQuestion>) {
    fun toJson(): JSONObject = JSONObject().put("kind", "structured_question")
        .put("interaction_id", interactionId).put("session_id", sessionId).put("title", title).put("mode", mode)
        .put("questions", JSONArray().apply { questions.forEach { question ->
            put(JSONObject().put("question", question.question).put("header", question.header)
                .put("multiSelect", question.multiSelect).put("options", JSONArray().apply {
                    question.options.forEach { option -> put(JSONObject().put("label", option.label)
                        .put("description", option.description).put("preview", option.preview)) }
                }))
        } })
    companion object {
        fun fromJson(json: JSONObject): AgentQuestionInteraction {
            require(json.optString("kind") == "structured_question")
            require(json.optString("interaction_id").isNotBlank() && json.optString("session_id").isNotBlank()) {
                "提问事件缺少必要信息"
            }
            val questions = json.getJSONArray("questions")
            require(questions.length() in 1..4)
            return AgentQuestionInteraction(json.getString("interaction_id"), json.getString("session_id"),
                json.optString("title", "需要你的选择"), json.optString("mode", "query"),
                (0 until questions.length()).map { index ->
                    val question = questions.getJSONObject(index)
                    val options = question.getJSONArray("options")
                    require(options.length() in 2..4)
                    AgentQuestion(question.getString("question"), question.getString("header"),
                        (0 until options.length()).map { optionIndex ->
                            val option = options.getJSONObject(optionIndex)
                            AgentQuestionOption(option.getString("label"), option.getString("description"), if (option.isNull("preview")) "" else option.optString("preview"))
                        }, question.optBoolean("multiSelect"))
                })
        }
    }
}
