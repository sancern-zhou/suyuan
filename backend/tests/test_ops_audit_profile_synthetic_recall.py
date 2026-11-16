"""组分站档案合成召回门禁（2026-11-14 扩展验证产物，永久守门）。

从 sup_form_profiles.yaml 全量档案自动合成三类用例：
  1. 违规值 → 对应规则必须命中（召回）；
  2. 合规值 → 对应规则不得命中（无误报）；
  3. 异常值 + 配对备注 → 豁免降级不硬判（备注联动）。
档案演进（新增/修改规则）时用例自动随之扩展，防止"档案写了规则、引擎不触发"
或"改阈值后合法值被误报"两类回归。无法安全合成用例的 spec（表达式区间无法
构造、日期无可判谓词等）按白名单跳过并打印统计。
"""

import math
from datetime import date, datetime, timedelta

import pytest

from app.services.ops_audit.config import load_sup_form_profiles
from app.services.ops_audit.rules.sup_form_rules import (
    ABNORMAL_RULE_ID,
    DATE_RULE_ID,
    FORMULA_RULE_ID,
    RANGE_RULE_ID,
    REQUIRED_RULE_ID,
    check_sup_form_rules,
    evaluate_formula,
)

DOCS = load_sup_form_profiles()["form_profiles"]
CHECKDATE = "2026-06-15"


def _run(tag, form):
    issues = []
    payload = {"RULEITEMTAG": tag, "WORKINGORDERCODE": "CH_SYNTH",
               "CHECKDATE": CHECKDATE, "CREATETIME": "2026-06-15 10:00:00"}
    payload.update(form)
    check_sup_form_rules({"WORKINGORDERCODE": "CH_SYNTH"}, [("SUP_RF_SYNTH", payload)],
                         issues, [], [])
    return issues


def _hit(issues, rule_id):
    return any(i.rule_id == rule_id for i in issues)


def _range_bounds(spec):
    """返回 (brand, min, max, value_type)；无可用区间返回 None。"""
    lo, hi = spec.get("min"), spec.get("max")
    brand = None
    if spec.get("brand_ranges"):
        brand, rng = next(iter(spec["brand_ranges"].items()))
        lo, hi = rng.get("min"), rng.get("max")
    if lo is None and hi is None:
        return None
    return brand, lo, hi, str(spec.get("value_type") or "").strip().lower() or None


def _range_values(spec, lo, hi, value_type):
    """构造 (越界值, 合规值)；数值文本直接可用（parse_form_number 兼容裸数）。"""
    duration = value_type == "duration_seconds"
    if lo is not None and hi is not None:
        bad = float(lo) - max(1.0, abs(float(lo)) * 0.01)
        good = (float(lo) + float(hi)) / 2  # 中点必在闭区间内（窄区间如 [0.999,1]）
    elif lo is not None:
        bad = float(lo) - max(1.0, abs(float(lo)) * 0.01)
        good = float(lo) + max(0.1, abs(float(lo)) * 0.01)
    else:
        bad = float(hi) + max(1.0, abs(float(hi)) * 0.01)
        good = float(hi) - max(0.1, abs(float(hi)) * 0.01)
    if duration:
        # 时长列用裸数（按秒）表达，避免单位歧义
        return f"{abs(bad) + 60:.0f}", f"{max(good, 1.0):.0f}"
    return f"{bad:.4f}".rstrip("0").rstrip("."), f"{good:.4f}".rstrip("0").rstrip(".")


def _expression_range_cases(tag, spec, idx):
    """表达式区间：用倍乘试探构造越界/合规输入。"""
    inputs = [str(i) for i in (spec.get("inputs") or [])]
    lo, hi = spec.get("min"), spec.get("max")
    if not inputs or (lo is None and hi is None):
        return []
    cases = []
    base_form = {"RULEITEMTAG": tag, "WORKINGORDERCODE": "CH_SYNTH"}
    for name in inputs:
        base_form[name] = "1"
    value = evaluate_formula(base_form, str(spec.get("expression") or ""), inputs)
    if value is None:
        for name in inputs:
            base_form[name] = "2"
        value = evaluate_formula(base_form, str(spec.get("expression") or ""), inputs)
    if value is None or isinstance(value, complex) or (isinstance(value, float) and math.isnan(value)):
        return []
    out = None
    for mult in (1, 2, 5, 10, 100, -1):
        trial_form = dict(base_form)
        for name in inputs:
            trial_form[name] = f"{float(base_form[name]) * mult}"
        trial = evaluate_formula(trial_form, str(spec.get("expression") or ""), inputs)
        if trial is None or isinstance(trial, complex) or (isinstance(trial, float) and math.isnan(trial)):
            continue
        if (lo is not None and trial < float(lo)) or (hi is not None and trial > float(hi)):
            out = (mult, trial)
            break
    label = str(spec.get("label") or spec.get("expression"))[:24]
    if out is not None:
        mult = out[0]
        bad_form = dict(base_form)
        for name in inputs:
            bad_form[name] = f"{float(base_form[name]) * mult}"
        cases.append((f"{tag}#rexpr{idx}:{label}:violate", tag,
                      {**bad_form, "CHECKDATE": CHECKDATE}, RANGE_RULE_ID, True))
        # 合规输入即 base（全部 1），若 base 恰在区间内则生成合规用例
        if (lo is None or value >= float(lo)) and (hi is None or value <= float(hi)):
            cases.append((f"{tag}#rexpr{idx}:{label}:ok", tag,
                          {**base_form, "CHECKDATE": CHECKDATE}, RANGE_RULE_ID, False))
    return cases


def _collect():
    cases = []
    skipped = {"expr_range": 0, "expr_formula": 0, "date_no_predicate": 0}
    for tag, profile in sorted(DOCS.items()):
        if profile.get("enabled") is False:
            continue
        for idx, spec in enumerate(profile.get("range_columns") or []):
            if spec.get("expression"):
                cases.extend(_expression_range_cases(tag, spec, idx))
                if not any(c[0].startswith(f"{tag}#rexpr{idx}") for c in cases):
                    skipped["expr_range"] += 1
                continue
            bounds = _range_bounds(spec)
            if bounds is None:
                skipped["expr_range"] += 1
                continue
            brand, lo, hi, value_type = bounds
            bad, good = _range_values(spec, lo, hi, value_type)
            column = str(spec.get("column") or "")
            label = str(spec.get("label") or column)[:24]
            form_bad = {column: bad, "CHECKDATE": CHECKDATE}
            form_ok = {column: good, "CHECKDATE": CHECKDATE}
            if brand:
                form_bad["DEVICEBRAND"] = brand
                form_ok["DEVICEBRAND"] = brand
            cases.append((f"{tag}#r{idx}:{label}:violate", tag, form_bad, RANGE_RULE_ID, True))
            cases.append((f"{tag}#r{idx}:{label}:ok", tag, form_ok, RANGE_RULE_ID, False))
            remarks = spec.get("remark_column")
            if remarks:
                first = remarks[0] if isinstance(remarks, (list, tuple)) else remarks
                form_exempt = {**form_bad, first: "维修处理中，已恢复"}
                # range 备注语义=降级人工复核，条目仍产出（消息含"需人工复核"）
                cases.append((f"{tag}#r{idx}:{label}:remark-downgrade", tag, form_exempt,
                              RANGE_RULE_ID, True))
        abnormal_specs = profile.get("abnormal_columns") or []
        if abnormal_specs:
            spec = abnormal_specs[0]
            column = str(spec.get("column") or "")
            bad_value = str((spec.get("values") or ["1"])[0])
            remarks = spec.get("remark_column")
            label = str(spec.get("label") or column)[:24]
            cases.append((f"{tag}#ab{0}:{label}:violate", tag,
                          {column: bad_value, "CHECKDATE": CHECKDATE}, ABNORMAL_RULE_ID, True))
            if remarks:
                first = remarks[0] if isinstance(remarks, (list, tuple)) else remarks
                cases.append((f"{tag}#ab{0}:{label}:remark-exempt", tag,
                              {column: bad_value, first: "已现场处理恢复正常", "CHECKDATE": CHECKDATE},
                              ABNORMAL_RULE_ID, False))
        for idx, spec in enumerate(profile.get("required_value_columns") or []):
            column = str(spec.get("column") or "")
            label = str(spec.get("label") or column)[:24]
            cases.append((f"{tag}#q{idx}:{label}:empty-hit", tag,
                          {column: "/", "CHECKDATE": CHECKDATE}, REQUIRED_RULE_ID, True))
            cases.append((f"{tag}#q{idx}:{label}:filled-ok", tag,
                          {column: "5", "CHECKDATE": CHECKDATE}, REQUIRED_RULE_ID, False))
            break  # 每档一条代表用例，控制用例总量
        for idx, spec in enumerate(profile.get("formula_columns") or []):
            inputs = [str(i) for i in (spec.get("inputs") or [])]
            target = str(spec.get("target") or "")
            if not inputs or not target:
                skipped["expr_formula"] += 1
                continue
            base_form = {"RULEITEMTAG": tag, "WORKINGORDERCODE": "CH_SYNTH",
                         "CHECKDATE": CHECKDATE}
            for name in inputs:
                base_form[name] = "1"
            expected = evaluate_formula(base_form, str(spec.get("expression") or ""), inputs)
            if expected is None:
                for name in inputs:
                    base_form[name] = "2"
                expected = evaluate_formula(base_form, str(spec.get("expression") or ""), inputs)
            if expected is None or (isinstance(expected, float) and math.isnan(expected)):
                skipped["expr_formula"] += 1
                continue
            label = str(spec.get("label") or target)[:24]
            cases.append((f"{tag}#f{idx}:{label}:ok", tag, dict(base_form), FORMULA_RULE_ID, False))
            bad_value = float(expected) + max(1.0, abs(float(expected)) * 0.5)
            bad_form = dict(base_form)
            bad_form[target] = f"{bad_value:.4f}"
            cases.append((f"{tag}#f{idx}:{label}:violate", tag, bad_form, FORMULA_RULE_ID, True))
        for idx, spec in enumerate(profile.get("date_columns") or []):
            start_col = str(spec.get("start") or "")
            end_col = str(spec.get("end") or "")
            label = str(spec.get("label") or start_col)[:24]
            if start_col and end_col and spec.get("must_cover_checkdate"):
                bad = {start_col: "2026-01-01", end_col: "2026-01-02", "CHECKDATE": CHECKDATE}
                intervals = spec.get("valid_intervals_days")
                span = (int(intervals[0]) + int(spec.get("interval_tolerance_days") or 0)) if intervals else 200
                # covered：start 取检查日前 span//2 天，end=start+span，保证区间有效且覆盖检查日
                start_d = date(2026, 6, 15) - timedelta(days=max(span // 2, 3))
                end_d = start_d + timedelta(days=span)
                cases.append((f"{tag}#d{idx}:{label}:expired", tag, bad, DATE_RULE_ID, True))
                cases.append((f"{tag}#d{idx}:{label}:covered", tag,
                              {start_col: start_d.isoformat(), end_col: end_d.isoformat(),
                               "CHECKDATE": CHECKDATE},
                              DATE_RULE_ID, False))
            elif start_col and not end_col and spec.get("single_date_rule"):
                rule = str(spec.get("single_date_rule"))
                if rule == "not_past":
                    cases.append((f"{tag}#d{idx}:{label}:past-violate", tag,
                                  {start_col: "2020-01-01", "CHECKDATE": CHECKDATE}, DATE_RULE_ID, True))
                    cases.append((f"{tag}#d{idx}:{label}:future-ok", tag,
                                  {start_col: "2027-06-01", "CHECKDATE": CHECKDATE}, DATE_RULE_ID, False))
                elif rule == "not_future":
                    cases.append((f"{tag}#d{idx}:{label}:future-violate", tag,
                                  {start_col: "2028-01-01", "CHECKDATE": CHECKDATE}, DATE_RULE_ID, True))
                    cases.append((f"{tag}#d{idx}:{label}:past-ok", tag,
                                  {start_col: "2026-01-01", "CHECKDATE": CHECKDATE}, DATE_RULE_ID, False))
            else:
                skipped["date_no_predicate"] += 1
    return cases, skipped


CASES, SKIPPED = _collect()


def test_case_inventory_sanity():
    """合成用例规模守门：档案扩展后用例必须随之增长（当前基线 700+）。"""
    assert len(CASES) >= 500, f"合成用例仅 {len(CASES)} 条，档案解析可能异常"
    assert SKIPPED["expr_range"] + SKIPPED["expr_formula"] + SKIPPED["date_no_predicate"] < 120


@pytest.mark.parametrize(
    "case_id,tag,form,rule_id,expect_hit",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_synthetic_recall(case_id, tag, form, rule_id, expect_hit):
    issues = _run(tag, form)
    hit = _hit(issues, rule_id)
    assert hit is expect_hit, (
        f"期望{'命中' if expect_hit else '不命中'} {rule_id}，实际"
        f"{'命中' if hit else '未命中'}；form={json.dumps(form, ensure_ascii=False)}；"
        f"issues={[i.rule_id for i in issues]}"
    )


import json  # noqa: E402  （置于文件尾仅供断言消息使用）
