from app.api.exam_routes import _publication_errors
from app.exam.models import ExamQuestion


def test_published_question_requires_a_valid_answer_and_source_reference():
    question = ExamQuestion(
        id="q-review",
        question_type="single_choice",
        topic="行政处罚",
        stem="哪项正确？",
        options={"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
        correct_answer="A",
        source_refs=[],
    )
    errors = _publication_errors(question)
    assert "missing_source_refs" in errors
    assert "missing_evidence_chunks" in errors


def test_grounded_question_can_pass_publication_validation():
    question = ExamQuestion(
        id="q-review-valid",
        question_type="multiple_choice",
        topic="自动监控",
        stem="哪些要求正确？",
        options={"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
        correct_answer=["A", "C"],
        source_refs=[{
            "knowledge_base_id": "kb",
            "document_id": "doc",
            "chunk_indices": [1, 2],
        }],
    )
    assert _publication_errors(question) == []
