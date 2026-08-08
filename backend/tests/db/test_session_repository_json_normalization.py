import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import UUID

from app.db.session_repository import SessionRepository


class _State(Enum):
    READY = "ready"


def test_message_json_fields_normalize_nested_runtime_values():
    moment = datetime(2026, 8, 9, 2, 24, 19, tzinfo=timezone.utc)
    identifier = UUID("12345678-1234-5678-1234-567812345678")
    message = {
        "type": "tool_result",
        "content": [{"updated_at": moment, "path": Path("reports/result.pdf")}],
        "data": {
            "amount": Decimal("12.5"),
            "identifier": identifier,
            "state": _State.READY,
            "dates": (date(2026, 8, 9), time(2, 24, 19)),
            "tags": {"second", "first"},
        },
        "request_context": {"started_at": moment},
    }

    content = SessionRepository._serialize_content(message["content"])
    data = SessionRepository._message_data(message)
    metadata = SessionRepository._message_metadata(message)

    assert content == [
        {
            "updated_at": "2026-08-09T02:24:19+00:00",
            "path": "reports/result.pdf",
        }
    ]
    assert data == {
        "amount": 12.5,
        "identifier": str(identifier),
        "state": "ready",
        "dates": ["2026-08-09", "02:24:19"],
        "tags": ["first", "second"],
    }
    assert metadata == {
        "request_context": {"started_at": "2026-08-09T02:24:19+00:00"}
    }

    json.dumps({"content": content, "data": data, "metadata": metadata})


def test_legacy_decimal_helper_uses_complete_json_normalization():
    value = SessionRepository._convert_decimal_to_float(
        {"updated_at": datetime(2026, 8, 9), "amount": Decimal("1.25")}
    )

    assert value == {"updated_at": "2026-08-09T00:00:00", "amount": 1.25}
