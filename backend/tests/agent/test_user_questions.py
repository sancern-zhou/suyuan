import pytest
from fastapi import HTTPException

from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.session.models import Session
from app.agent.user_questions import QuestionSet, validate_answers
from app.api import agent as agent_api
from app.tools.social.ask_user_question_tool import AskUserQuestionTool


QUESTIONS = [
    {
        "question": "选择输出格式？",
        "header": "格式",
        "options": [
            {"label": "PDF", "description": "固定版式"},
            {"label": "HTML", "description": "网页浏览"},
        ],
        "multiSelect": False,
    },
    {
        "question": "需要哪些章节？",
        "header": "章节",
        "options": [
            {"label": "摘要", "description": "概览"},
            {"label": "附录", "description": "原始数据"},
        ],
        "multiSelect": True,
    },
]


def test_question_validation_and_answers():
    assert len(QuestionSet.model_validate({"questions": QUESTIONS}).questions) == 2
    with pytest.raises(ValueError):
        QuestionSet.model_validate({"questions": [QUESTIONS[0]] * 2})
    with pytest.raises(ValueError):
        QuestionSet.model_validate({"questions": [{
            **QUESTIONS[0], "options": [QUESTIONS[0]["options"][0]] * 2,
        }]})
    assert validate_answers(QUESTIONS, [
        {"selected": [0]}, {"selected": [0, 1], "custom": "图表"},
    ])[1]["custom"] == "图表"
    for invalid in (
        [{"selected": [0, 1]}, {"selected": [0]}],
        [{"selected": [3]}, {"selected": [0]}],
        [{"selected": []}, {"selected": [0]}],
        [{"selected": [0]}, {"selected": [1, 1]}],
        [{"selected": [True]}, {"selected": [0]}],
    ):
        with pytest.raises(ValueError):
            validate_answers(QUESTIONS, invalid)


@pytest.mark.asyncio
async def test_tool_result_exposes_interaction_and_parallel_runtime_recognizes_it():
    result = await AskUserQuestionTool().execute(questions=QUESTIONS)
    assert result["success"] is True
    assert result["status"] == "awaiting_user"
    assert result["data"] == {}
    assert result["metadata"]["schema_version"] == "v2.0"
    assert AgentRuntime._interaction_from_observation(result)["kind"] == "structured_question"
    parallel = {"tool_results": [{"result": result}]}
    assert AgentRuntime._interaction_from_observation(parallel)["questions"][0]["options"][0]["label"] == "PDF"


@pytest.mark.asyncio
async def test_unattended_call_cannot_pause_for_a_user():
    class Context:
        runtime_metadata = {"agent_depth": 1}

    result = await AskUserQuestionTool().execute(Context(), QUESTIONS)
    assert result["success"] is False
    assert AgentRuntime._interaction_from_observation(result) is None


@pytest.mark.asyncio
async def test_answer_resolution_persists_and_rejects_stale_or_invalid(monkeypatch):
    session = Session(
        session_id="question-session", query="制作报告",
        metadata={"pending_interaction": {
            "interaction_id": "interaction-1",
            "kind": "structured_question",
            "questions": QUESTIONS,
            "mode": "assistant",
        }},
    )

    class Manager:
        async def load_session(self, session_id):
            return session

        async def save_session_metadata(self, value):
            return True

    class Catalog:
        async def require_write(self, session_id, user):
            pass

    monkeypatch.setattr(agent_api, "get_session_manager", lambda: Manager())
    with pytest.raises(HTTPException) as invalid:
        await agent_api.resolve_agent_interaction(
            "question-session", "interaction-1",
            agent_api.AgentInteractionResolution(decision="answer", answers=[{"selected": [0]}]),
            user=object(), catalog=Catalog(),
        )
    assert invalid.value.status_code == 422
    assert "pending_interaction" in session.metadata

    response = await agent_api.resolve_agent_interaction(
        "question-session", "interaction-1",
        agent_api.AgentInteractionResolution(
            decision="answer", answers=[{"selected": [0]}, {"selected": [1]}]
        ),
        user=object(), catalog=Catalog(),
    )
    assert response["mode"] == "assistant"
    assert "PDF" in response["resume_query"]
    assert "附录" in response["resume_query"]
    assert "pending_interaction" not in session.metadata
    with pytest.raises(HTTPException) as stale:
        await agent_api.resolve_agent_interaction(
            "question-session", "interaction-1",
            agent_api.AgentInteractionResolution(decision="reject"),
            user=object(), catalog=Catalog(),
        )
    assert stale.value.status_code == 404
