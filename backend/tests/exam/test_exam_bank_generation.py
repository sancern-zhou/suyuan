from app.exam.bank_generation import (
    ExamBankGenerationService,
    SourceBatch,
    build_source_batches,
    validate_candidate,
)


def test_source_batches_preserve_document_chunk_indices():
    batches = build_source_batches(
        "doc-1",
        "行政处罚法.pdf",
        [
            {"chunk_index": 3, "content": "第一段" * 10},
            {"chunk_index": 4, "content": "第二段" * 10},
        ],
        max_chars=50,
    )

    assert [batch.chunk_indices for batch in batches] == [(3,), (4,)]
    assert "[chunk_index=3]" in batches[0].text


def test_candidate_validation_rejects_unsupported_or_ambiguous_choice_question():
    errors = validate_candidate(
        {
            "question_type": "single_choice",
            "stem": "哪一项正确？",
            "options": {"A": "甲", "B": "乙", "C": "丙"},
            "correct_answer": ["A", "B"],
            "evidence_chunk_indices": [99],
        },
        {1, 2},
    )

    assert "evidence_outside_source_batch" in errors
    assert "choice_options_must_be_abcd" in errors
    assert "single_choice_requires_one_answer" in errors


def test_candidate_validation_accepts_grounded_multiple_choice():
    errors = validate_candidate(
        {
            "question_type": "multiple_choice",
            "stem": "哪些属于法定要求？",
            "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            "correct_answer": ["A", "C"],
            "evidence_chunk_indices": [1, 2],
        },
        {1, 2, 3},
    )
    assert errors == []


def test_generation_prompt_requires_exact_machine_readable_field_names():
    prompt = ExamBankGenerationService._generation_prompt(
        SourceBatch("doc-1", "行政处罚法.pdf", (3,), "[chunk_index=3]\n原文")
    )

    assert '"question_type": "single_choice"' in prompt
    assert '"stem": "题干"' in prompt
    assert "不得改名、翻译字段名" in prompt
