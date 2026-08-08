import json

from app.agent.memory.tool_protocol_repair import (
    SYNTHETIC_TOOL_RESULT_CONTENT,
    repair_tool_result_pairing,
)


def _assistant_tool_use(tool_id: str, tool_name: str = "query_data"):
    return {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": tool_id,
                "name": tool_name,
                "input": {"q": tool_id},
            }
        ],
    }


def _user_tool_result(tool_id: str, content: str = "ok"):
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps({"summary": content}, ensure_ascii=False),
                "is_error": False,
            }
        ],
    }


def test_repair_tool_result_pairing_keeps_valid_adjacent_pair():
    messages = [_assistant_tool_use("toolu_1"), _user_tool_result("toolu_1")]

    repaired = repair_tool_result_pairing(messages)

    assert repaired == messages


def test_repair_tool_result_pairing_drops_orphan_tool_result():
    messages = [
        {"role": "user", "content": "hello"},
        _user_tool_result("toolu_orphan"),
    ]

    repaired = repair_tool_result_pairing(messages)

    assert repaired == [{"role": "user", "content": "hello"}]


def test_repair_tool_result_pairing_conservative_drops_missing_tool_result():
    messages = [
        {"role": "user", "content": "start"},
        _assistant_tool_use("toolu_missing"),
        {"role": "assistant", "content": "after"},
    ]

    repaired = repair_tool_result_pairing(messages, strategy="conservative")

    assert repaired == [
        {"role": "user", "content": "start"},
        {"role": "assistant", "content": "after"},
    ]


def test_repair_tool_result_pairing_api_safe_inserts_synthetic_result():
    messages = [_assistant_tool_use("toolu_missing")]

    repaired = repair_tool_result_pairing(messages, strategy="api_safe")

    assert repaired == [
        _assistant_tool_use("toolu_missing"),
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_missing",
                    "content": SYNTHETIC_TOOL_RESULT_CONTENT,
                    "is_error": True,
                }
            ],
        },
    ]


def test_repair_tool_result_pairing_deduplicates_tool_use_and_tool_result_ids():
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "query_data",
                    "input": {"q": 1},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "query_data",
                    "input": {"q": 2},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "first",
                    "is_error": False,
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "duplicate",
                    "is_error": False,
                },
            ],
        },
    ]

    repaired = repair_tool_result_pairing(messages)

    assert repaired == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "query_data",
                    "input": {"q": 1},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "first",
                    "is_error": False,
                }
            ],
        },
    ]
