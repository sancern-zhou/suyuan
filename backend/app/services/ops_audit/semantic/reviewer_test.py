import json

from app.services.ops_audit.semantic import prompts, reviewer


def test_review_text_includes_rf_field_row_explanations():
    text = reviewer._compose_review_text(
        {"ORDERTITLE": "任务检查单"},
        [],
        [
            (
                "RF_W_GASEOUSCHECK_NOX",
                {
                    "REMARK": "",
                    "PMTCHECKVALUE": "0.002",
                    "PMTCHECKROW": "表格范围有误",
                },
            )
        ],
    )

    assert "RF_W_GASEOUSCHECK_NOX.PMTCHECKROW:表格范围有误" in text


def test_review_text_includes_rf_handling_record_explanations():
    text = reviewer._compose_review_text(
        {"ORDERTITLE": "任务检查单"},
        [],
        [
            (
                "RF_W_GASEOUSCHECK_NOX",
                {
                    "REMARK": "",
                    "PMTCHECKVALUE": "0.018",
                    "EXCEPTIONHANDLINGRECORD": "厂家文件范围：0～4.096 v",
                    "异常时处理记录": "厂家文件范围：0～4.096 v",
                },
            )
        ],
    )

    assert "RF_W_GASEOUSCHECK_NOX.EXCEPTIONHANDLINGRECORD:厂家文件范围：0～4.096 v" in text
    assert "RF_W_GASEOUSCHECK_NOX.异常时处理记录:厂家文件范围：0～4.096 v" in text


def test_remark_batch_payload_includes_issue_evidence_summary(monkeypatch):
    captured = {}

    def fake_call(prompt, text, *, context=None):
        captured["prompt"] = prompt
        captured["text"] = text
        return {
            "results": [
                {
                    "working_order_code": "WO-NOX-PMT",
                    "judgment_type": "valid",
                    "is_complete": True,
                    "has_cause": True,
                    "has_action": True,
                    "has_result": True,
                    "problem_description": "",
                    "confidence": 0.95,
                }
            ]
        }

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fake_call)
    issue = {
        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
        "category": "异常说明问题",
        "severity": "高",
        "field": "rf.RF_W_GASEOUSCHECK_NOX.remark",
        "message": "RF表单存在异常/漏填/错配，需语义判断备注是否解释充分: NOx周检参考PMT信号检查值(0.018)超出FPI品牌正常范围(1.5-4.096 V)",
        "evidence": json.dumps(
            {
                "working_order_code": "WO-NOX-PMT",
                "rf_table": "RF_W_GASEOUSCHECK_NOX",
                "reason_rule_id": "RF_RANGE_OUT_OF_SPEC",
                "abnormal_field": "rf.RF_W_GASEOUSCHECK_NOX.PMTCHECKVALUE",
                "abnormal_message": "NOx周检参考PMT信号检查值(0.018)超出FPI品牌正常范围(1.5-4.096 V)",
                "remark_candidates": {
                    "EXCEPTIONHANDLINGRECORD": "厂家文件范围：0～4.096 v"
                },
                "needs_semantic_review": True,
            },
            ensure_ascii=False,
        ),
    }
    task = {
        "working_order_code": "WO-NOX-PMT",
        "review_kind": "remark_semantics",
        "semantic_focus": ["RF_ABNORMAL_VALUE_NO_REMARK"],
        "evidence_summary": {
            "matched_rules": ["RF_ABNORMAL_VALUE_NO_REMARK"],
            "sample_issues": [issue],
        },
    }

    result = reviewer._review_remark_tasks_batch(
        [task],
        {"WO-NOX-PMT": {"scoring_issues": [issue]}},
        {"WO-NOX-PMT": {}},
        {},
        {"WO-NOX-PMT": []},
    )

    payload = json.loads(captured["text"])
    item = payload["items"][0]
    assert captured["prompt"] == prompts.REMARK_BATCH_SEMANTIC_JSON_PROMPT
    assert item["evidence_summary"]["sample_issues"][0]["evidence"]
    assert "厂家文件范围：0～4.096 v" in item["evidence_summary"]["sample_issues"][0]["evidence"]
    assert result["WO-NOX-PMT"]["judgment"] == "cleared"


def test_remark_batch_prompt_mentions_pm_temp_calibration_situation():
    assert "RF_PM_TEMP_ERROR_OUT_OF_RANGE" in prompts.REMARK_BATCH_SEMANTIC_JSON_PROMPT
    assert "calibration_situation" in prompts.REMARK_BATCH_SEMANTIC_JSON_PROMPT
    assert "校准情况" in prompts.REMARK_BATCH_SEMANTIC_JSON_PROMPT


def test_pm_tape_candidate_is_not_promoted_by_generic_remark_review(monkeypatch):
    def fake_call(prompt, text, *, context=None):
        if prompt == prompts.PM_TAPE_USAGE_BATCH_JSON_PROMPT:
            return {
                "results": [
                    {
                        "item_id": "WO-1::PM10::TAPEUSAGEDISPOSAL",
                        "is_valid": True,
                        "reason": "纸带够一周使用量，可支撑到下次维护。",
                        "problem_description": "纸带使用量及处置情况为“够一周使用量”，可判断纸带足够使用到下次维护。",
                    }
                ]
            }
        if prompt == prompts.REMARK_BATCH_SEMANTIC_JSON_PROMPT:
            return {
                "results": [
                    {
                        "working_order_code": "WO-1",
                        "is_complete": False,
                        "has_cause": False,
                        "has_action": False,
                        "has_result": False,
                        "problem_description": "备注内容仅为“任务检查单”，未说明异常原因、处置措施和处理结果。",
                        "confidence": 0.95,
                    }
                ]
            }
        raise AssertionError(f"unexpected prompt: {prompt}")

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fake_call)
    abnormal_issue = {
        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
        "category": "异常说明问题",
        "severity": "高",
        "field": "rf.RF_W_GASEOUSCHECK_O3.remark",
        "message": "RF表单存在异常/漏填/错配但无有效说明: O3周检测量信号A检查值超出正常范围",
        "evidence": json.dumps(
            {
                "working_order_code": "WO-1",
                "rf_table": "RF_W_GASEOUSCHECK_O3",
                "reason_rule_id": "RF_RANGE_OUT_OF_SPEC",
                "abnormal_field": "rf.RF_W_GASEOUSCHECK_O3.GYCHECKVALUE",
                "abnormal_message": "O3周检测量信号A检查值超出正常范围",
                "remark_candidates": {"REMARK": ""},
                "needs_semantic_review": False,
            },
            ensure_ascii=False,
        ),
    }
    pm_tape_issue = {
        "rule_id": "RF_PM_TAPE_USAGE_INVALID",
        "category": "规范性问题",
        "severity": "中",
        "field": "rf.RF_W_PMCHECK.TAPEUSAGEDISPOSAL",
        "message": "颗粒物周检纸带使用量及处置情况需复核: 够一周使用量",
        "evidence": json.dumps(
            {
                "working_order_code": "WO-1",
                "rf_table": "RF_W_PMCHECK",
                "pollutant_type": "PM10",
                "device_model": "MP101",
                "instrument_type": "paper_tape",
                "field": "TAPEUSAGEDISPOSAL",
                "field_label": "纸带使用量及处置情况",
                "value": "够一周使用量",
                "needs_semantic_review": True,
            },
            ensure_ascii=False,
        ),
    }
    audit = {
        "records": [
            {
                "working_order_code": "WO-1",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "finish_time": "2026-06-09 15:27:16",
                "audit_level": "有问题",
                "deterministic_issue_count": 1,
                "candidate_issue_count": 1,
                "attachment_count": 0,
                "attachment_review_rules": [],
                "workflow_steps": ["CreateOrder", "CheckOrder"],
                "rf_tables": ["RF_W_GASEOUSCHECK_O3", "RF_W_PMCHECK"],
                "scoring_issues": [abnormal_issue, pm_tape_issue],
            }
        ]
    }

    results = reviewer.build_semantic_review_results(audit, {"orders": [], "details": [], "rf_forms": {}})

    confirmed_rule_sets = [
        set(result.get("supported_rule_ids", []))
        for result in results["results"]
        if result.get("judgment") == "confirmed_issue"
    ]
    pm_results = [
        result
        for result in results["results"]
        if result.get("field_label") == "纸带使用量及处置情况"
    ]
    assert {"RF_ABNORMAL_VALUE_NO_REMARK"} in confirmed_rule_sets
    assert {"RF_PM_TAPE_USAGE_INVALID"} not in confirmed_rule_sets
    assert pm_results
    assert all(result.get("judgment") == "cleared" for result in pm_results)


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


def test_no_device_review_clears_plain_none_even_when_model_marks_insufficient(monkeypatch):
    def fake_call(prompt, text, *, context=None):
        return {
            "results": [
                {
                    "item_id": "WO-1::0",
                    "is_explained": False,
                    "reason": "模拟模型仍按旧口径认为无是低信息内容。",
                    "problem_description": "能见度设备型号为/，运行情况为无，未说明原因。",
                    "confidence": 0.95,
                }
            ]
        }

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fake_call)
    evidence = {
        "violations": [
            {
                "label": "能见度设备",
                "model_field": "VISIBILITYDEVICEMODEL",
                "model_value": "/",
                "situation_field": "VISIBILITYSITUATION",
                "situation_value": "无",
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
    assert result["can_promote_to_final_issue"] is False
    assert result["remark_review"]["problem_description"] == ""
