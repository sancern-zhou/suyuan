"""18 条真实问题案例回归（组分站审核二期）。

案例来源：projects/guangdong/docs/sup-audit-cases/（三份人工排查记录）。
工单数据为案例描述时点的状态重建（部分工单已退回修改，本地库为整改后数据，
需还原案例时点才能回归）；真实库命中的字段值以注释标注来源。

验收口径（二期计划阶段 2.5）：预期命中 ≥ 14。视觉水印（博罗石下）与依赖
设备台账/字段语义普查的案例为已知确定性盲区，逐条注明原因。
"""

from __future__ import annotations

import pytest

from app.services.ops_work_order_audit_engine import audit_dataset

SUP = "SUP_RF_COMMON"


def _order(code, station_id, create_time, order_type="SupCheck", maintenance_type="Week"):
    return {
        "WORKINGORDERCODE": code,
        "STATIONID": station_id,
        "DDWORKINGORDERTYPE": order_type,
        "MAINTENANCETYPE": maintenance_type,
        "CREATETIME": create_time,
        "DDWORKINGORDERSTATUS": "Finish",
    }


def _form(tag, pollutant, checkdate, **columns):
    form = {
        "WORKINGORDERCODE": "",
        "RULEITEMTAG": tag,
        "POLLUTANTTYPE": pollutant,
        "CHECKDATE": checkdate,
    }
    form.update(columns)
    return form


def _file(typecode, filename, created="2026-09-24 10:31:37"):
    return {"REFID": "", "TYPECODE": typecode, "FILENAME": filename, "CREATEDATE": created}


def _jpg(tag, pollutant, name, **kw):
    return _file(f"{tag}_{pollutant}", name, **kw)


# ---------------------------------------------------------------------------
# 案例夹具：code → (order, forms, files, 期望规则, 是否已知盲区)
# ---------------------------------------------------------------------------


def _case_fixtures():
    fixtures: list[dict] = []

    # 案例 1（②）：深圳莲花山甲醛仪/CO2/NH3、盐田港 BC/甲烷非甲烷工单填写不及时。
    # 无工单号，按周质控口径重建：检查日 9/14，创建 9/25（滞后 11 天 > 周允许 7 天）。
    fixtures.append(
        {
            "case": "案例1 深圳莲花山/盐田港 填写不及时",
            "order": _order("CH_CASE01_SHENZHEN", "SZ_LHS", "2026-09-25 10:00:00"),
            "forms": [
                _form("Sup_RF_Week_NMHCQC", "NMHC", "2026-09-14 00:00:00"),
            ],
            "files": [_jpg("Sup_RF_Week_NMHCQC", "NMHC", "甲烷非甲烷零点核查.jpg")],
            "expected": {"SUP_CYCLE_TIMELINESS"},
        }
    )

    # 案例 2（④）：惠州江北（周）BC 工单应提供 BC 仪器相关附件（CH2609141789390375203）。
    # 已知盲区：组分站设备台账缺失（一期已知），无法从工单侧判定"该单应为 BC 工单"。
    fixtures.append(
        {
            "case": "案例2 惠州江北 BC 工单缺 BC 附件",
            "order": _order("CH2609141789390375203", "48", "2026-09-14 20:52:55"),
            "forms": [
                _form("Sup_RF_Week_NMHCQC", "NMHC", "2026-09-14 00:00:00"),
            ],
            "files": [
                _jpg("Sup_RF_Week_NMHCQC", "NMHC", "甲烷非甲烷零点核查.jpg"),
                _file("Sup_RF_Week_NMHCQC_NMHC", "2026年09月08日甲烷非甲烷分析仪质控检查.xlsx"),
            ],
            "expected": set(),
            "known_miss": "组分站设备台账缺失，工单设备维度（BC）不可得，待台账同步后纳入",
        }
    )

    # 案例 3（①）：湛江吴川振文 3 单年度维护检定未上传年度预防报告
    # （CH2609151789444950681 / CH2609201789890889196 / CH2609201789895985888）。
    # 报告于 9/30 退回整改后补传，此处还原案例时点（仅过程照片）。
    for code, pollutant, create in (
        ("CH2609151789444950681", "NMHC", "2026-09-15 12:02:30"),
        ("CH2609201789890889196", "N2O", "2026-09-20 17:19:45"),
        ("CH2609201789895985888", "PM1", "2026-09-20 17:19:45"),
    ):
        fixtures.append(
            {
                "case": f"案例3 吴川振文 {pollutant} 年检缺报告",
                "order": _order(code, "33", create, maintenance_type="Year"),
                "forms": [
                    _form("Sup_RF_PDLIYearCheck", pollutant, "2026-09-15 00:00:00"),
                ],
                "files": [
                    _jpg("Sup_RF_PDLIYearCheck", pollutant, "气路清洁.jpg"),
                    _jpg("Sup_RF_PDLIYearCheck", pollutant, "仪器内部清洁.jpg"),
                    _jpg("Sup_RF_PDLIYearCheck", pollutant, "雨帽清洁.jpg"),
                ],
                "expected": {"SUP_ATTACHMENT_REQUIRED_MISSING"},
            }
        )

    # 案例 4（③）：湛江吴川振文 N2O 流量月核查示值误差>±2% 未重新校准。
    # 已知盲区：该工单本地 sup_rf_common 无表单（已退回），N2O 月核查表单类型
    # 未能定位，示值误差阈值需业务确认。
    fixtures.append(
        {
            "case": "案例4 吴川振文 N2O 示值误差",
            "order": _order("CH_CASE04_N2O", "33", "2026-09-20 17:19:45", maintenance_type="Year"),
            "forms": [],
            "files": [],
            "expected": set(),
            "known_miss": "表单类型未定位且阈值需业务确认，待档案补充后纳入",
        }
    )

    # 案例 5（⑤）：韶关市八中 OCEC 周巡检升温程序数值空白（CH2609161789542767165）。
    # 工单退回后 OCEC 表单已从本地库删除，按案例描述还原空白数值。
    fixtures.append(
        {
            "case": "案例5 韶关八中 OCEC 升温程序数值空白",
            "order": _order("CH_CASE05_SGOCEC", "9", "2026-09-16 15:12:47"),
            "forms": [
                _form(
                    "Sup_RF_OCECJGWeekCheck",
                    "OCEC",
                    "2026-09-16 00:00:00",
                    string29="80/60/80",
                    string30="20/20/20",
                    string33=None,
                    string35=None,
                    string42=None,
                    string43=None,
                    string44=None,
                    string45=None,
                ),
            ],
            "files": [],
            "expected": {"SUP_REQUIRED_VALUE_EMPTY"},
        }
    )

    # 案例 6（①）：丰顺八乡山 9/24 BC 年度维护检定缺完整维护报告
    # （CH2609241790216699673）——真实库当前即为 6 张过程照片、无报告。
    fixtures.append(
        {
            "case": "案例6 丰顺八乡山 BC 年检缺报告",
            "order": _order("CH2609241790216699673", "FS_BXS", "2026-09-24 10:24:59", maintenance_type="Year"),
            "forms": [
                _form("Sup_RF_PDLIYearCheck", "BC", "2026-09-23 00:00:00"),
            ],
            "files": [
                _jpg("Sup_RF_PDLIYearCheck", "BC", "气路清洁.jpg"),
                _jpg("Sup_RF_PDLIYearCheck", "BC", "稳定性测试 (7).jpg"),
                _jpg("Sup_RF_PDLIYearCheck", "BC", "零点测试 (5).jpg"),
                _jpg("Sup_RF_PDLIYearCheck", "BC", "仪器内部清洁.jpg"),
                _jpg("Sup_RF_PDLIYearCheck", "BC", "支架稳定.jpg"),
                _jpg("Sup_RF_PDLIYearCheck", "BC", "雨帽清洁.jpg"),
            ],
            "expected": {"SUP_ATTACHMENT_REQUIRED_MISSING"},
        }
    )

    # 案例 7（②）：云浮牧羊 NH3 季度工单填写不及时（无工单号）。
    # 按季度周期口径重建：检查日 8/1，创建 9/10（滞后 40 天 > 季度允许 31 天）。
    fixtures.append(
        {
            "case": "案例7 云浮牧羊 NH3 季度不及时",
            "order": _order("CH_CASE07_YFMY", "YF_MY", "2026-09-10 10:00:00", maintenance_type="Quarter"),
            "forms": [
                _form("Sup_RF_PANsFlowCheck", "NH3", "2026-08-01 00:00:00"),
            ],
            "files": [],
            "expected": {"SUP_CYCLE_TIMELINESS"},
        }
    )

    # 案例 8（①）：河源江东 9/30 PM1 年度维护检定缺完整维护报告
    # （CH2609301790739494912）。
    fixtures.append(
        {
            "case": "案例8 河源江东 PM1 年检缺报告",
            "order": _order("CH2609301790739494912", "HY_JD", "2026-09-30 11:38:14", maintenance_type="Year"),
            "forms": [
                _form("Sup_RF_PDLIYearCheck", "PM1", "2026-09-30 00:00:00"),
            ],
            "files": [
                _jpg("Sup_RF_PDLIYearCheck", "PM1", "仪器内部清洁.jpg"),
                _jpg("Sup_RF_PDLIYearCheck", "PM1", "支架稳定.jpg"),
            ],
            "expected": {"SUP_ATTACHMENT_REQUIRED_MISSING"},
        }
    )

    # 案例 9（④）：博罗石下周质控附件照片水印为河源站点（CH2609281790563610130）。
    # 已知盲区：水印地点/经纬度比对属视觉试点（二期阶段 2.3），非确定性规则。
    fixtures.append(
        {
            "case": "案例9 博罗石下附件水印站点不符",
            "order": _order("CH2609281790563610130", "23", "2026-09-28 10:46:50"),
            "forms": [
                _form("Sup_RF_Week_NMHCQC", "NMHC", "2026-09-28 00:00:00"),
            ],
            "files": [
                _file("Sup_RF_Week_NMHCQC_NMHC", "NMHC监测仪零气空白等质控数据-9月23日.xlsx"),
                _jpg("Sup_RF_Week_NMHCQC", "NMHC", "单点.jpg"),
            ],
            "expected": set(),
            "known_miss": "水印地点比对属视觉试点（阶段 2.3），确定性规则不做地点判定",
        }
    )

    # 案例 10（②）：湛江海大甲烷半年工单填写不及时（无工单号）。
    # 检查日 8/1，创建 9/20（滞后 50 天 > 半年允许 45 天）。
    fixtures.append(
        {
            "case": "案例10 湛江海大甲烷半年不及时",
            "order": _order("CH_CASE10_ZJHD", "ZJ_HD", "2026-09-20 10:00:00", maintenance_type="HalfYear"),
            "forms": [
                _form("Sup_RF_HY_NMHCMaintenanceRecord", "NMHC", "2026-08-01 00:00:00"),
            ],
            "files": [_jpg("Sup_RF_HY_NMHCMaintenanceRecord", "NMHC", "甲烷维护.jpg")],
            "expected": {"SUP_CYCLE_TIMELINESS"},
        }
    )

    # 案例 11（③）：清远技师学院 OCEC 温度偏差填写有误（CH2610031791032964037）。
    # 案例时点偏差列填了绝对温度（如 851.3），整改后为 0.15%/0.02%；还原案例时点。
    fixtures.append(
        {
            "case": "案例11 清远 OCEC 温度偏差填绝对温度",
            "order": _order("CH_CASE11_QYOCEC", "10", "2026-10-03 21:09:23"),
            "forms": [
                _form(
                    "Sup_RF_OCECJGWeekCheck",
                    "OCEC",
                    "2026-09-30 00:00:00",
                    string33="851.3",
                    string35="850.2",
                    string42="851.3",
                    string43="加热温度会上下浮动",
                    string44="850.2",
                ),
            ],
            "files": [],
            "expected": {"SUP_RANGE_OUT_OF_SPEC"},
        }
    )

    # 案例 12（①）：韶关市八中 NH3 采样管检查附件缺失（CH2609291790660589498）。
    # 已知盲区：采样管检查为表单内 bool 题目项级别要求，且该 NH3 表单未同步本地。
    fixtures.append(
        {
            "case": "案例12 韶关八中 NH3 采样管附件缺失",
            "order": _order("CH2609291790660589498", "9", "2026-09-29 13:43:09"),
            "forms": [
                _form("Sup_RF_WeekSecurityCheck", "ZF", "2026-09-29 00:00:00"),
            ],
            "files": [
                _jpg("Sup_RF_WeekSecurityCheck", "ZF", "空调.jpg"),
                _jpg("Sup_RF_WeekSecurityCheck", "ZF", "灭火器.jpg"),
            ],
            "expected": set(),
            "known_miss": "采样管检查为 bool 题目项级要求且 NH3 表单未同步，待列语义普查后纳入",
        }
    )

    # 案例 13（③）：潮州西园路 PANs 设定误差复算不符（CH2609041788520167552）。
    # 真实案例行数据：三个流量点误差均按流量计读数误算（如点 2 填 0.5%，
    # 按仪器读数复算应为 27.7%），工单已退回修改。
    fixtures.append(
        {
            "case": "案例13 潮州西园路 PANs 设定误差",
            "order": _order("CH2609041788520167552", "30", "2026-09-04 19:09:27", maintenance_type="Quarter"),
            "forms": [
                _form(
                    "Sup_RF_PANsFlowCheck",
                    "PANs",
                    "2026-09-04 00:00:00",
                    string13="992.13",
                    string14="1063",
                    string15="973.857",
                    string16="1.88%",
                    string17="4.04",
                    string18="5.16",
                    string19="4.06",
                    string20="0.5%",
                    string21="19.80",
                    string22="22.23",
                    string23="19.442",
                    string24="-1.84",
                ),
            ],
            "files": [],
            "expected": {"SUP_FORMULA_RECALC"},
        }
    )

    # 案例 14（②）：惠州江北质控结果超期，应上传 8/31-9/6 一周质控结果
    # （CH2609071788748201535）——真实库数据：xlsx 数据日期 8/30，检查日 9/7。
    fixtures.append(
        {
            "case": "案例14 惠州江北质控超期",
            "order": _order("CH2609071788748201535", "48", "2026-09-07 10:30:01"),
            "forms": [
                _form("Sup_RF_Week_NMHCQC", "NMHC", "2026-09-07 00:00:00"),
            ],
            "files": [
                _file("Sup_RF_Week_NMHCQC_NMHC", "2026年8月30日甲烷非甲烷分析仪质控检查.xlsx"),
                _jpg("Sup_RF_Week_NMHCQC", "NMHC", "甲烷非甲烷零点核查.jpg"),
            ],
            "expected": {"SUP_CYCLE_TIMELINESS"},
        }
    )

    # 案例 15（①）：龙川细坳 N2O 更换滤膜附件缺失（案例文档工单号与案例 16 相同，
    # 判定为笔误；N2O 巡检表单未同步本地库）。
    fixtures.append(
        {
            "case": "案例15 龙川细坳 N2O 换滤膜附件缺失",
            "order": _order("CH_CASE15_LCX", "LC_XC", "2026-09-07 20:19:30"),
            "forms": [],
            "files": [],
            "expected": set(),
            "known_miss": "N2O 巡检表单未同步本地，更换滤膜为题目项级附件要求，待表单接入后纳入",
        }
    )

    # 案例 16（⑥）：惠州下埔甲烷动态校准仪日期有误（CH2609071788783570920）。
    # 真实库数据：校准 8/11→有效期 10/6，间隔 56 天，非标准周期档位。
    fixtures.append(
        {
            "case": "案例16 惠州下埔动态校准仪日期有误",
            "order": _order("CH2609071788783570920", "35", "2026-09-07 20:39:03"),
            "forms": [
                _form(
                    "Sup_RF_Week_NMHCQC",
                    "NMHC",
                    "2026-09-07 00:00:00",
                    time1="2026-01-28 00:00:00",
                    time2="2027-01-27 00:00:00",
                    time3="2026-08-11 00:00:00",
                    time4="2026-10-06 00:00:00",
                ),
            ],
            "files": [
                _file("Sup_RF_Week_NMHCQC_NMHC", "2026年8月30日甲烷非甲烷分析仪质控检查.xlsx"),
                _jpg("Sup_RF_Week_NMHCQC", "NMHC", "甲烷非甲烷零点核查.jpg"),
            ],
            "expected": {"SUP_DATE_REASONABLENESS"},
        }
    )

    # 案例 17（⑥）：东莞东城甲醛标准溶液有效日期填写错误，有效期应一个月内
    # （CH2606281782647943168）。还原案例时点：配制 6/28、有效期 8/28（61 天）。
    fixtures.append(
        {
            "case": "案例17 东莞东城甲醛标液有效期",
            "order": _order("CH2606281782647943168", "21", "2026-06-28 19:59:03"),
            "forms": [
                _form(
                    "Sup_RF_Week_HONOCheck",
                    "HCHO",
                    "2026-07-01 00:00:00",
                    time1="2026-06-28 00:00:00",
                    time2="2026-08-28 00:00:00",
                ),
            ],
            "files": [],
            "expected": {"SUP_DATE_REASONABLENESS"},
        }
    )

    # 案例 18（⑦）：江门鹤山水溶性离子柱压超范围未备注（CH2608301788101238626）。
    # 已知盲区：柱压数值在 xlsx 数据附件内，需数据文件读数规则（同 O3 量值传递
    # XLS 模式），本期仅完成档案 groundwork（range_note）。
    fixtures.append(
        {
            "case": "案例18 江门鹤山柱压超范围未备注",
            "order": _order("CH2608301788101238626", "5", "2026-08-30 22:47:18"),
            "forms": [
                _form("Sup_RF_WaterSolubleIonsQuality", "WaterSolubleIons", "2026-08-27 00:00:00"),
            ],
            "files": [
                _file("Sup_RF_WaterSolubleIonsQuality_WaterSolubleIons", "气体-气溶胶水溶性离子质控记录表2026年8月27日.xlsx"),
            ],
            "expected": set(),
            "known_miss": "柱压数值在 xlsx 数据文件内，待数据文件读数规则扩展后纳入",
        }
    )

    return fixtures


def _sup_dataset(fixtures):
    orders = []
    forms_by_code: dict[str, list[dict]] = {}
    files: list[dict] = []
    for fixture in fixtures:
        order = fixture["order"]
        code = order["WORKINGORDERCODE"]
        orders.append(order)
        forms_by_code[code] = []
        for form in fixture["forms"]:
            form = dict(form)
            form["WORKINGORDERCODE"] = code
            form["STATIONID"] = order["STATIONID"]
            forms_by_code[code].append(form)
        for record in fixture["files"]:
            record = dict(record)
            record["REFID"] = code
            files.append(record)
    return {
        "orders": orders,
        "details": [],
        "stations": [],
        "devices": [],
        "rf_forms": {SUP: [form for group in forms_by_code.values() for form in group]},
        "attachments": [],
        "wo_commonfile": files,
    }


@pytest.fixture(scope="module")
def sup_audit():
    fixtures = _case_fixtures()
    audit = audit_dataset(_sup_dataset(fixtures), enable_visual=False)
    hits_by_code = {
        record["working_order_code"]: {issue["rule_id"] for issue in record["issues"]}
        for record in audit["records"]
    }
    return fixtures, hits_by_code


def test_case18_regression_expected_rules(sup_audit):
    """逐案例断言预期命中规则（已知盲区单独断言并注明原因）。"""

    fixtures, hits_by_code = sup_audit
    # 18 条案例 → 20 个工单夹具（吴川振文 3 单分别建夹具）。
    assert len(fixtures) == 20

    for fixture in fixtures:
        code = fixture["order"]["WORKINGORDERCODE"]
        actual = hits_by_code.get(code, set())
        for rule_id in fixture["expected"]:
            assert rule_id in actual, f"{fixture['case']}（{code}）未命中 {rule_id}：{sorted(actual)}"


def test_case18_regression_hit_count_meets_plan(sup_audit):
    """验收口径：≥14 命中（吴川 3 单分别计数，共 18 单口径）。"""

    fixtures, hits_by_code = sup_audit
    hit_orders = sum(
        1
        for fixture in fixtures
        if fixture["expected"]
        and fixture["expected"] <= hits_by_code.get(fixture["order"]["WORKINGORDERCODE"], set())
    )
    known_misses = [fixture["case"] for fixture in fixtures if fixture.get("known_miss")]
    assert hit_orders >= 14, f"仅命中 {hit_orders}/18；已知盲区：{known_misses}"


def test_case18_known_misses_do_not_fire_unexpected_rules(sup_audit):
    """盲区案例不产生其他 SUP_* 误报（避免用噪声掩盖盲区）。"""

    fixtures, hits_by_code = sup_audit
    for fixture in fixtures:
        if not fixture.get("known_miss"):
            continue
        code = fixture["order"]["WORKINGORDERCODE"]
        actual = {
            rule_id
            for rule_id in hits_by_code.get(code, set())
            if rule_id.startswith("SUP_")
        }
        unexpected = actual - fixture["expected"]
        assert not unexpected, f"{fixture['case']} 出现非预期 SUP 规则：{sorted(unexpected)}"


def test_mainnet_forms_are_not_affected_by_sup_rules(sup_audit):
    """主网表单（无 RULEITEMTAG）不触发 SUP_* 规则。"""

    dataset = {
        "orders": [_order("CH_MAINSTREAM", "S1", "2026-09-07 10:00:00", "Check", "Week")],
        "details": [],
        "stations": [],
        "devices": [],
        "rf_forms": {
            "RF_W_INSPECTION": [
                {
                    "WORKINGORDERCODE": "CH_MAINSTREAM",
                    "STATIONID": "S1",
                    "string16": "999%",
                    "time3": "2026-08-11 00:00:00",
                    "time4": "2026-10-06 00:00:00",
                    "CHECKDATE": "2026-09-07 00:00:00",
                }
            ]
        },
        "attachments": [],
        "wo_commonfile": [],
    }
    audit = audit_dataset(dataset, enable_visual=False)
    rule_ids = {issue["rule_id"] for issue in audit["records"][0]["issues"]}
    assert not {rule for rule in rule_ids if rule.startswith("SUP_")}
