import json

from app.services.ops_audit.semantic import prompts, reviewer


def test_no_device_review_uses_specific_problem_description(monkeypatch):
    problem_description = (
        "城市摄像设备型号填写为/，运行情况为“城市摄影系统故障，历史交接遗留”；"
        "该说明描述了运行异常，但未解释型号字段为何占位。"
    )

    def fake_call(prompt, text, *, context=None):
        return {
            "results": [
                {
                    "item_id": "WO-1::0",
                    "is_explained": False,
                    "reason": "故障描述不能解释型号占位原因。",
                    "problem_description": problem_description,
                    "confidence": 0.98,
                }
            ]
        }

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fake_call)
    evidence = {
        "violations": [
            {
                "label": "城市摄像设备",
                "model_field": "CITYCAMERADEVICEMODEL",
                "model_value": "/",
                "situation_field": "CITYCAMERASITUATION",
                "situation_value": "城市摄影系统故障，历史交接遗留",
            }
        ]
    }
    task = {
        "working_order_code": "WO-1",
        "station_id": "ST-1",
        "review_kind": "remark_semantics",
        "semantic_focus": ["RF_NO_DEVICE_WITHOUT_REMARK"],
        "evidence_summary": {
            "sample_issues": [
                {
                    "rule_id": "RF_NO_DEVICE_WITHOUT_REMARK",
                    "evidence": json.dumps(evidence, ensure_ascii=False),
                }
            ]
        },
    }

    result = reviewer._review_no_device_tasks_batch([task], {}, {}, {}, {})["WO-1"]

    assert result["judgment"] == "confirmed_issue"
    assert result["conclusion"] == problem_description
    assert result["remark_review"]["problem_description"] == problem_description
    assert result["rf_table"] == "RF_W_OTHERDEVICECHECK"
    assert result["rf_field"] == "CITYCAMERADEVICEMODEL"
    assert result["field"] == "rf.RF_W_OTHERDEVICECHECK.CITYCAMERADEVICEMODEL"
    assert result["field_label"] == "城市摄像设备"


def test_no_device_prompt_is_about_placeholder_reason_not_only_no_device():
    prompt = prompts.NO_DEVICE_BATCH_JSON_PROMPT

    assert "型号字段为何缺失或占位" in prompt
    assert "故障" in prompt
    assert "problem_description" in prompt


def test_pm_tape_prompt_explains_model_based_business_logic_and_problem_detail():
    prompt = prompts.PM_TAPE_USAGE_BATCH_JSON_PROMPT

    assert "device_model" in prompt
    assert "instrument_type" in prompt
    assert "1405" in prompt
    assert "TAPEUSAGEDISPOSAL" in prompt
    assert "TEOMMEMBRANEDISPOSAL" in prompt
    assert "核查目标" in prompt
    assert "能否支撑到下次维护" in prompt
    assert "不要把判断限定为固定关键词" in prompt
    assert "判为不规范时" in prompt
    assert "无法核查" in prompt
    assert "problem_description" in prompt


def test_remark_prompt_explains_range_out_of_spec_handling_record_logic():
    prompt = prompts.REMARK_BATCH_SEMANTIC_JSON_PROMPT

    assert "RF_RANGE_OUT_OF_SPEC" in prompt
    assert "异常时处理记录" in prompt
    assert "超出品牌正常范围" in prompt
    assert "恢复正常" in prompt
    assert "不可直接判定为问题" in prompt
    assert "problem_description" in prompt


def test_no_device_review_cleared_conclusion_uses_placeholder_reason_language(monkeypatch):
    def fake_call(prompt, text, *, context=None):
        return {
            "results": [
                {
                    "item_id": "WO-1::0",
                    "is_explained": True,
                    "reason": "运行情况解释了型号占位原因。",
                    "problem_description": "",
                    "confidence": 0.95,
                }
            ]
        }

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fake_call)
    evidence = {
        "violations": [
            {
                "label": "城市摄像设备",
                "model_field": "CITYCAMERADEVICEMODEL",
                "model_value": "/",
                "situation_field": "CITYCAMERASITUATION",
                "situation_value": "城市摄影系统故障，历史交接遗留",
            }
        ]
    }
    task = {
        "working_order_code": "WO-1",
        "semantic_focus": ["RF_NO_DEVICE_WITHOUT_REMARK"],
        "evidence_summary": {
            "sample_issues": [
                {
                    "rule_id": "RF_NO_DEVICE_WITHOUT_REMARK",
                    "evidence": json.dumps(evidence, ensure_ascii=False),
                }
            ]
        },
    }

    result = reviewer._review_no_device_tasks_batch([task], {}, {}, {}, {})["WO-1"]

    assert result["judgment"] == "cleared"
    assert result["conclusion"] == "运行情况已能合理解释型号字段缺失或占位原因。"
