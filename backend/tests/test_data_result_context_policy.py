from app.agent.context.data_result_policy import (
    INLINE_RECORD_LIMIT,
    persist_large_inline_data,
    shape_data_result_for_context,
)


def _records(count: int):
    return [
        {
            "index": index,
            "name": f"row-{index}",
            **({"optional": None} if index == count - 1 else {}),
        }
        for index in range(count)
    ]


def test_small_dataset_is_complete_in_context():
    records = _records(INLINE_RECORD_LIMIT)
    result = shape_data_result_for_context({
        "success": True,
        "data": records,
        "file_path": "/tmp/full.json",
        "metadata": {},
    })

    assert result["data"] == records
    assert result["data_complete"] is True
    assert result["record_count"] == INLINE_RECORD_LIMIT
    assert result["returned_records"] == INLINE_RECORD_LIMIT
    assert result["sample_strategy"] == "complete"


def test_large_dataset_returns_schema_and_head_tail_sample():
    records = _records(INLINE_RECORD_LIMIT + 6)
    result = shape_data_result_for_context({
        "success": True,
        "data": records,
        "file_path": "/tmp/full.json",
        "metadata": {},
    })

    assert len(result["data"]) == INLINE_RECORD_LIMIT
    assert [row["index"] for row in result["data"][:2]] == [0, 1]
    assert [row["index"] for row in result["data"][-2:]] == [28, 29]
    assert result["data_complete"] is False
    assert result["record_count"] == 30
    assert result["returned_records"] == INLINE_RECORD_LIMIT
    assert result["sample_strategy"] == "head_tail"
    fields = {item["name"]: item for item in result["field_schema"]}
    assert fields["index"]["types"] == ["integer"]
    assert fields["optional"]["present_count"] == 1
    assert result["metadata"]["context_data"]["inline_record_limit"] == 24


def test_large_dataset_without_file_path_is_not_silently_discarded():
    records = _records(INLINE_RECORD_LIMIT + 1)
    result = shape_data_result_for_context({
        "success": True,
        "data": records,
        "metadata": {},
    })

    assert result["data"] == records
    assert result["data_complete"] is True
    assert result["sample_strategy"] == "complete_no_file_path"


def test_existing_tool_sample_uses_declared_total_count():
    sample = _records(5)
    result = shape_data_result_for_context({
        "success": True,
        "data": sample,
        "file_path": "/tmp/full.json",
        "metadata": {"total_count": 500},
    })

    assert result["data"] == sample
    assert result["data_complete"] is False
    assert result["record_count"] == 500
    assert result["returned_records"] == 5
    assert result["sample_strategy"] == "provided_sample"


def test_large_unexternalized_data_is_persisted_before_sampling():
    class Context:
        def save_data(self, data, schema, metadata):
            self.saved = (data, schema, metadata)
            return "/data/session/query.json"

    context = Context()
    records = _records(INLINE_RECORD_LIMIT + 1)
    persisted = persist_large_inline_data(
        {"success": True, "data": records, "metadata": {}},
        context=context,
        tool_name="query_example",
    )
    shaped = shape_data_result_for_context(persisted)

    assert persisted["file_path"] == "/data/session/query.json"
    assert context.saved[0] == records
    assert len(shaped["data"]) == INLINE_RECORD_LIMIT
    assert shaped["data_complete"] is False
