"""江西省噪声平台接口目录与参数契约（单一来源）。

发现式接入的目录层：新增平台接口时只改本文件 + 客户端 API_ROUTES 各一条，
不再新增独立 LLM 工具，避免工具 schema 常驻上下文膨胀（AGENTS.md
「上下文注入选型策略」的 describe_table 模式）。

- search_jiangxi_noise_apis：按关键词在本目录检索接口；
- describe_jiangxi_noise_api：按需取单个接口的参数契约；
- call_jiangxi_noise_api：校验并执行调用。

params 契约字段（平台 DTO 字段名为键）：
- type: string | int | float | bool | datetime | string_list | datetime_list | int_list
- required: 是否必填
- desc: 中文说明
- enum: 可选；{标签: 值} 映射（call 时按标签解析为值）或取值列表
- default: 可选默认值
"""

from __future__ import annotations

from typing import Any

# TimeType 公共枚举（平台 TimeTypeEnum：日30/周35/月40/季45/半年50/年55）
_TIME_TYPE = {
    "type": "int",
    "enum": {"day": 30, "week": 35, "month": 40, "quarter": 45, "half_year": 50, "year": 55},
    "desc": "统计周期类型：day=日、week=周、month=月、quarter=季、half_year=半年、year=年",
}
_DATA_TYPE = {
    "type": "int",
    "enum": {"raw": 0, "audited": 1},
    "default": 0,
    "desc": "数据类型：raw=原始数据，audited=审核数据",
}
_STATION_TYPE_OPTIONAL = {
    "type": "int",
    "required": False,
    "enum": {"0类": 3, "1类": 4, "2类": 5, "3类": 6, "4a类": 7, "4b类": 8},
    "desc": "声环境功能区类型；留空=全部功能区",
}
_NOISE_TYPE_OPTIONAL = {
    "type": "int",
    "required": False,
    "enum": {"自然": 1, "施工": 2, "交通": 3, "工业": 4, "生活": 5},
    "desc": "声源类型筛选；留空=全部",
}

# —— 运维/台账域共享参数（ABP 分页基类与常见过滤字段） ——
_PAGED_PARAMS = {
    "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
    "maxResultCount": {"type": "int", "required": False, "default": 10, "desc": "每页条数(1-100)"},
}
_OPT_START_TIME = {"type": "datetime", "required": False, "desc": "开始时间(含)"}
_OPT_END_TIME = {
    "type": "datetime",
    "required": False,
    "desc": "结束时间(平台多为开区间，不含该时刻；建议传次日零时)",
}
_STATION_MULTI = {
    "type": "string",
    "required": False,
    "desc": "站点编码，多个用英文逗号分隔",
}
_TIMEPOINT_RANGE = {
    "type": "datetime_list",
    "required": False,
    "desc": "日期范围 [开始, 结束]；一个=当天，两个=闭区间(最多两个)",
}
_CODES_OPTIONAL = {"type": "string_list", "required": False, "desc": "区域/点位编码列表；留空=全部"}

API_CATALOG: dict[str, dict[str, Any]] = {
    # —— 已有独立工具的接口同样登记，保持目录完整 ——
    "alarm_analysis": {
        "summary": "超标事件统计分析：总数/处理状态/级别分布/区域与站点排名/事件明细",
        "keywords": ["超标", "超限", "事件", "报警", "排名", "明细", "处理"],
        "route": "alarm_analysis",
        "returns": "超标汇总、级别分布、区域/站点排名与事件明细列表",
        "note": "也可直接调用独立工具 get_jiangxi_noise_alarm_analysis",
        "params": {
            "TimeType": {
                "type": "string",
                "required": True,
                "enum": {"today": "today", "lastDay": "lastDay", "7day": "7day", "month": "month"},
                "desc": "统计时段：today=今日、lastDay=昨日、7day=近7天、month=本月",
            },
            "CityCode": {
                "type": "string",
                "required": False,
                "desc": "6位城市编码或360000全省；留空=全省",
            },
            "DistrictCode": {"type": "string", "required": False, "desc": "区县编码"},
        },
        "example": {"TimeType": "month", "CityCode": "360100"},
    },
    "compliance_statistics": {
        "summary": "达标统计：城市/功能区/站点三级昼夜达标率（须恰好一个自然周期）",
        "keywords": ["达标", "达标率", "统计", "昼夜", "合格"],
        "route": "compliance_statistics",
        "returns": "汇总+城市/功能区/站点三级达标率行",
        "note": "也可直接调用独立工具 get_jiangxi_noise_compliance(report=statistics)",
        "params": {
            "CityCodes": {"type": "string_list", "required": True, "desc": "城市编码列表"},
            "DataType": _DATA_TYPE,
            "TimeType": {
                "type": "int",
                "required": True,
                "enum": {"day": 30, "month": 40, "quarter": 45, "year": 55},
                "desc": "统计周期；起止日期须落在同一自然周期内",
            },
            "StartDate": {"type": "datetime", "required": True, "desc": "周期首日"},
            "EndDate": {"type": "datetime", "required": True, "desc": "周期最后一日（闭区间）"},
        },
        "example": {
            "CityCodes": ["360100"],
            "DataType": 1,
            "TimeType": 40,
            "StartDate": "2026-07-01 00:00:00",
            "EndDate": "2026-07-31 00:00:00",
        },
    },
    "compliance_comparison": {
        "summary": "达标对比：剔除异常气象数据前后的昼/夜达标天数变化",
        "keywords": ["达标", "对比", "气象", "剔除", "天数"],
        "route": "compliance_comparison",
        "returns": "按城市/区县/站型的达标天数前后对比分页列表",
        "note": "也可直接调用独立工具 get_jiangxi_noise_compliance(report=comparison)",
        "params": {
            "CityCodes": {"type": "string_list", "required": False, "desc": "城市编码列表"},
            "DistrictCodes": {"type": "string_list", "required": False, "desc": "区县编码列表"},
            "DataType": _DATA_TYPE,
            "StartDate": {"type": "datetime", "required": True, "desc": "开始日期"},
            "EndDate": {"type": "datetime", "required": True, "desc": "结束日期"},
            "SkipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "MaxResultCount": {"type": "int", "required": False, "default": 20, "desc": "每页条数"},
        },
        "example": {
            "CityCodes": ["360100"],
            "DataType": 1,
            "StartDate": "2026-01-01 00:00:00",
            "EndDate": "2026-01-31 00:00:00",
        },
    },
    # —— 本批新接入：报表与专项分析 ——
    "exceed_statistics": {
        "summary": "超标统计：按小时/季度/年度统计站点超标情况（PC 端超标统计分析口径）",
        "keywords": ["超标", "统计", "分析", "小时", "季度", "年度"],
        "route": "exceed_statistics",
        "returns": "超标统计结果（按所选维度）",
        "params": {
            "Dimension": {
                "type": "string",
                "required": True,
                "enum": {"hour": "hour", "quarter": "quarter", "year": "year"},
                "desc": "统计维度：hour=小时、quarter=季度、year=年度",
            },
            "Period": {
                "type": "string",
                "required": False,
                "enum": {"day": "day", "night": "night"},
                "desc": "季度/年度统计的时段：day=昼间、night=夜间",
            },
            "TimePoint": {"type": "datetime", "required": True, "desc": "所选周期内任一时间点"},
            "StationCodes": {
                "type": "string_list",
                "required": False,
                "desc": "站点编码列表；留空=全部功能区站点",
            },
            "DataType": _DATA_TYPE,
        },
        "example": {"Dimension": "quarter", "Period": "day", "TimePoint": "2026-07-15 00:00:00"},
    },
    "overlimit_analysis": {
        "summary": "超标分析：时段内超标事件按声源/点位排名（平均超标幅度或事件数）",
        "keywords": ["超标", "分析", "声源", "点位", "排名", "幅度"],
        "route": "overlimit_analysis",
        "returns": "超标点位排名与声源分布分析",
        "params": {
            "StartTime": {"type": "datetime", "required": True, "desc": "开始时间"},
            "EndTime": {"type": "datetime", "required": True, "desc": "结束时间"},
            "SourceName": {
                "type": "string",
                "required": False,
                "default": "all",
                "desc": "噪声源类型；空或 all=全部声源",
            },
            "RankingType": {
                "type": "string",
                "required": False,
                "enum": {"amount": "amount", "count": "count"},
                "default": "amount",
                "desc": "排名方式：amount=按平均超标幅度、count=按超标事件数",
            },
            "StationCodes": {
                "type": "string_list",
                "required": False,
                "desc": "站点编码列表；留空=全部功能区站点",
            },
            "DataType": _DATA_TYPE,
        },
        "example": {"StartTime": "2026-07-01 00:00:00", "EndTime": "2026-07-31 00:00:00"},
    },
    "season_comparison": {
        "summary": "季节对比：单站点各季节噪声水平对比（数据对比模拟）",
        "keywords": ["季节", "对比", "春夏秋冬", "站点"],
        "route": "season_comparison",
        "returns": "该站点分季节噪声对比数据",
        "params": {
            "StationCode": {"type": "string", "required": True, "desc": "站点编码"},
            "Date": {"type": "datetime", "required": True, "desc": "目标日期（确定对比年份）"},
            "DataType": _DATA_TYPE,
        },
        "example": {"StationCode": "1737A", "Date": "2026-07-15 00:00:00"},
    },
    "area_average_report": {
        "summary": "区域均值报表：城市/区县 Ld/Ln/Ldn 等指标周期报表",
        "keywords": ["区域", "均值", "报表", "城市", "区县"],
        "route": "area_average_report",
        "returns": "区域均值报表列表",
        "params": {
            "Codes": {"type": "string_list", "required": True, "desc": "城市/区县编码列表"},
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "起止时间列表 [开始, 结束]",
            },
            "TimeType": _TIME_TYPE,
            "DataType": _DATA_TYPE,
            "SandType": {
                "type": "int",
                "required": False,
                "enum": {"不扣沙": 0, "扣沙": 1},
                "default": 0,
                "desc": "沙尘天气数据是否剔除",
            },
            "SamplingType": {
                "type": "int",
                "required": False,
                "enum": {"原始": 0, "剔气象": 1},
                "desc": "抽样类型；留空=不筛选",
            },
        },
        "example": {
            "Codes": ["360100"],
            "TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"],
            "TimeType": 40,
        },
    },
    "district_report": {
        "summary": "区县报表：区县维度周期噪声评价报表",
        "keywords": ["区县", "报表", "评价", "区"],
        "route": "district_report",
        "returns": "区县评价报表列表",
        "params": {
            "Codes": {"type": "string_list", "required": True, "desc": "区县编码列表"},
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "起止时间列表 [开始, 结束]",
            },
            "TimeType": _TIME_TYPE,
            "DataType": _DATA_TYPE,
            "SandType": {
                "type": "int",
                "required": False,
                "enum": {"不扣沙": 0, "扣沙": 1},
                "default": 0,
                "desc": "沙尘天气数据是否剔除",
            },
            "SamplingType": {
                "type": "int",
                "required": False,
                "enum": {"原始": 0, "剔气象": 1},
                "desc": "抽样类型；留空=不筛选",
            },
        },
        "example": {
            "Codes": ["360102"],
            "TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"],
            "TimeType": 40,
        },
    },
    "assessment_report": {
        "summary": "考核报表：城市噪声分析研判/考核报告",
        "keywords": ["考核", "报告", "研判", "城市"],
        "route": "assessment_report",
        "returns": "考核报告数据",
        "params": {
            "CityCode": {"type": "string", "required": True, "desc": "城市编码"},
            "TimePoint": {"type": "datetime", "required": True, "desc": "周期内任一时间点"},
            "TimeType": _TIME_TYPE,
            "DataType": _DATA_TYPE,
        },
        "example": {"CityCode": "360100", "TimePoint": "2026-07-15 00:00:00", "TimeType": 40},
    },
    "prevention_control": {
        "summary": "噪声防治分析：站点集合的污染防治专项分析",
        "keywords": ["防治", "治理", "分析", "专项"],
        "route": "prevention_control",
        "returns": "防治专项分析结果",
        "params": {
            "StationCodes": {
                "type": "string_list",
                "required": False,
                "desc": "站点编码列表；留空=全部",
            },
            "TimePoint": {"type": "datetime", "required": True, "desc": "周期内任一时间点"},
            "TimeType": _TIME_TYPE,
            "DataType": _DATA_TYPE,
        },
        "example": {"TimePoint": "2026-07-15 00:00:00", "TimeType": 40},
    },
    "horizontal_overview": {
        "summary": "横向总览：指定城市与功能区类型的横向对比概览",
        "keywords": ["横向", "总览", "对比", "城市", "功能区"],
        "route": "horizontal_overview",
        "returns": "横向总览数据",
        "params": {
            "CityCode": {"type": "string", "required": True, "desc": "城市编码"},
            "Date": {
                "type": "datetime",
                "required": False,
                "desc": "目标日期；留空=最新",
            },
            "StationType": _STATION_TYPE_OPTIONAL,
            "DataType": _DATA_TYPE,
        },
        "example": {"CityCode": "360100"},
    },
    "noise_calendar": {
        "summary": "声日历：区域/站点逐日噪声评价值（日历视图数据）",
        "keywords": ["日历", "逐日", "每天", "月历"],
        "route": "noise_calendar",
        "returns": "逐日评价值列表",
        "params": {
            "RegionType": {
                "type": "int",
                "required": True,
                "enum": {"站点": 0, "区县": 1, "城市": 2, "省份": 3},
                "desc": "区域维度",
            },
            "Code": {"type": "string", "required": False, "desc": "区域/站点编码"},
            "StartDate": {"type": "datetime", "required": True, "desc": "开始日期"},
            "EndDate": {"type": "datetime", "required": True, "desc": "结束日期"},
            "DataType": _DATA_TYPE,
        },
        "example": {
            "RegionType": 2,
            "Code": "360100",
            "StartDate": "2026-07-01 00:00:00",
            "EndDate": "2026-07-31 00:00:00",
        },
    },
    "sound_calendar_day": {
        "summary": "声日历（日视图）：按年输出逐日声级矩阵，适合热力日历",
        "keywords": ["日历", "热力", "逐日", "年度"],
        "route": "sound_calendar_day",
        "returns": "按区域分组、按日组织的声级数据（分页）",
        "params": {
            "AnalysisDimension": {
                "type": "int",
                "required": True,
                "enum": {"城市": 1, "区县": 2, "站点": 3},
                "desc": "分析维度",
            },
            "StationCode": {
                "type": "string",
                "required": True,
                "desc": "对应维度的区域/站点编码",
            },
            "StartDay": {"type": "int", "required": True, "desc": "起始年份，例如 2026"},
            "EndDay": {"type": "int", "required": True, "desc": "结束年份，例如 2026"},
            "DataType": _DATA_TYPE,
            "SandType": {
                "type": "int",
                "required": False,
                "enum": {"不扣沙": 0, "扣沙": 1},
                "default": 0,
                "desc": "是否剔除沙尘",
            },
            "CalAreaType": {
                "type": "int",
                "required": False,
                "desc": "声功能区类型编码；留空=全部",
            },
            "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "maxResultCount": {"type": "int", "required": False, "default": 10, "desc": "每页条数"},
        },
        "example": {
            "AnalysisDimension": 3,
            "StationCode": "1737A",
            "StartDay": 2026,
            "EndDay": 2026,
        },
    },
    "sound_calendar_month": {
        "summary": "声日历（月视图）：按年输出逐月声级矩阵",
        "keywords": ["日历", "月历", "逐月", "年度"],
        "route": "sound_calendar_month",
        "returns": "按区域分组、按月组织的声级数据（分页）",
        "params": {
            "AnalysisDimension": {
                "type": "int",
                "required": True,
                "enum": {"城市": 1, "区县": 2, "站点": 3},
                "desc": "分析维度",
            },
            "StationCode": {
                "type": "string",
                "required": True,
                "desc": "对应维度的区域/站点编码",
            },
            "StartDay": {"type": "int", "required": True, "desc": "起始年份，例如 2026"},
            "EndDay": {"type": "int", "required": True, "desc": "结束年份，例如 2026"},
            "DataType": _DATA_TYPE,
            "SandType": {
                "type": "int",
                "required": False,
                "enum": {"不扣沙": 0, "扣沙": 1},
                "default": 0,
                "desc": "是否剔除沙尘",
            },
            "CalAreaType": {
                "type": "int",
                "required": False,
                "desc": "声功能区类型编码；留空=全部",
            },
            "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "maxResultCount": {"type": "int", "required": False, "default": 10, "desc": "每页条数"},
        },
        "example": {
            "AnalysisDimension": 3,
            "StationCode": "1737A",
            "StartDay": 2026,
            "EndDay": 2026,
        },
    },
    "assessment_ranking": {
        "summary": "考核排名：站点/区县/城市达标考核排名",
        "keywords": ["考核", "排名", "达标", "榜单"],
        "route": "assessment_ranking",
        "returns": "考核排名列表",
        "params": {
            "StationCodes": {
                "type": "string_list",
                "required": False,
                "desc": "站点编码列表；留空=全部功能区站点",
            },
            "StartDate": {"type": "datetime", "required": False, "desc": "开始日期"},
            "EndDate": {"type": "datetime", "required": False, "desc": "结束日期"},
            "DataType": {
                "type": "int",
                "required": True,
                "enum": {"raw": 0, "audited": 1},
                "desc": "数据类型：raw=原始、audited=审核",
            },
            "Dimension": {
                "type": "string",
                "required": False,
                "enum": {"all": "all", "city": "city", "area": "area", "station": "station"},
                "default": "all",
                "desc": "排名维度",
            },
        },
        "example": {"DataType": 1, "Dimension": "city", "StartDate": "2026-07-01 00:00:00",
                    "EndDate": "2026-07-31 00:00:00"},
    },
    "source_feature_analysis": {
        "summary": "噪声源特征分析：按区域统计各类声源特征占比",
        "keywords": ["噪声源", "特征", "声源", "占比", "结构"],
        "route": "source_feature_analysis",
        "returns": "声源特征分析结果",
        "params": {
            "Codes": {"type": "string_list", "required": False, "desc": "区域/站点编码列表"},
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "起止时间列表 [开始, 结束]",
            },
            "AreaType": {
                "type": "int",
                "required": True,
                "enum": {"市": 1, "区县": 2, "站点": 3},
                "desc": "统计维度",
            },
            "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "maxResultCount": {"type": "int", "required": False, "default": 20, "desc": "每页条数"},
        },
        "example": {"TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"], "AreaType": 2},
    },
    "source_identification_check": {
        "summary": "噪声源识别核查：声源类型占比与逐小时分布统计",
        "keywords": ["噪声源", "识别", "声源", "类型", "小时"],
        "route": "source_identification_check",
        "returns": "声源类型统计+逐小时分布",
        "params": {
            "Codes": {"type": "string_list", "required": False, "desc": "区域/站点编码列表"},
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "起止时间列表 [开始, 结束]",
            },
            "AreaType": {
                "type": "int",
                "required": True,
                "enum": {"市": 1, "区县": 2, "站点": 3},
                "desc": "统计维度",
            },
            "NoiseType": _NOISE_TYPE_OPTIONAL,
            "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "maxResultCount": {"type": "int", "required": False, "default": 20, "desc": "每页条数"},
        },
        "example": {"TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"], "AreaType": 3},
    },
    "source_identification_detail": {
        "summary": "噪声源识别明细：识别事件的分页明细列表",
        "keywords": ["噪声源", "识别", "明细", "事件"],
        "route": "source_identification_detail",
        "returns": "识别事件明细分页列表",
        "params": {
            "Codes": {"type": "string_list", "required": False, "desc": "区域/站点编码列表"},
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "起止时间列表 [开始, 结束]",
            },
            "AreaType": {
                "type": "int",
                "required": True,
                "enum": {"市": 1, "区县": 2, "站点": 3},
                "desc": "统计维度",
            },
            "NoiseType": _NOISE_TYPE_OPTIONAL,
            "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "maxResultCount": {"type": "int", "required": False, "default": 20, "desc": "每页条数"},
        },
        "example": {"TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"], "AreaType": 3},
    },
    "source_report": {
        "summary": "噪声源报告：区域噪声源结构分析报告",
        "keywords": ["噪声源", "报告", "结构", "溯源"],
        "route": "source_report",
        "returns": "噪声源结构报告",
        "params": {
            "Codes": {"type": "string_list", "required": False, "desc": "区域/站点编码列表"},
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "起止时间列表 [开始, 结束]",
            },
            "AreaType": {
                "type": "int",
                "required": True,
                "enum": {"市": 1, "区县": 2, "站点": 3},
                "desc": "统计维度",
            },
            "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "maxResultCount": {"type": "int", "required": False, "default": 20, "desc": "每页条数"},
        },
        "example": {"TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"], "AreaType": 2},
    },
    # —— 运维域查询 ——
    "substation_blank_records": {
        "summary": "子站空白(缺测)记录分页：数据缺失时段清单",
        "keywords": ["子站", "空白", "缺测", "记录", "运维"],
        "route": "substation_blank_records",
        "returns": "空白记录分页列表",
        "params": {
            "StationId": _STATION_MULTI,
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "substation_maintenance_records": {
        "summary": "子站维护记录分页：维护/巡检处置台账",
        "keywords": ["子站", "维护", "维修", "记录", "运维"],
        "route": "substation_maintenance_records",
        "returns": "维护记录分页列表",
        "params": {
            "StationId": _STATION_MULTI,
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "substation_maintenance_detail": {
        "summary": "子站维护记录详情（按记录主键）",
        "keywords": ["维护", "详情", "记录"],
        "route": "substation_maintenance_detail",
        "returns": "单条维护记录详情",
        "params": {"id": {"type": "int", "required": True, "desc": "记录主键"}},
        "example": {"id": 1},
    },
    "substation_video_events": {
        "summary": "子站视频事件分页：视频识别事件台账",
        "keywords": ["子站", "视频", "事件", "监控"],
        "route": "substation_video_events",
        "returns": "视频事件分页列表",
        "params": {
            "StationId": _STATION_MULTI,
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "substation_power_status": {
        "summary": "子站供电状态分页：站点供电/断电记录",
        "keywords": ["子站", "供电", "断电", "电源", "状态"],
        "route": "substation_power_status",
        "returns": "供电状态分页列表",
        "params": {
            "StationCode": _STATION_MULTI,
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "remote_calibration_logs": {
        "summary": "远程校准日志（全量列表，按校准时间倒序）",
        "keywords": ["校准", "远程", "日志", "标校"],
        "route": "remote_calibration_logs",
        "returns": "校准日志列表（全量，注意结果规模）",
        "params": {
            "StationCode": {
                "type": "string",
                "required": False,
                "desc": "站点编码，多个逗号分隔；提供时忽略 StationName",
            },
            "StationName": {
                "type": "string",
                "required": False,
                "desc": "站点名称精确匹配（仅 StationCode 为空时生效）",
            },
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
        },
        "example": {},
    },
    "remote_calibration_log_paged": {
        "summary": "远程校准日志分页查询",
        "keywords": ["校准", "日志", "分页"],
        "route": "remote_calibration_log_paged",
        "returns": "校准日志分页列表",
        "params": {
            "StationCode": _STATION_MULTI,
            "StationName": {
                "type": "string",
                "required": False,
                "desc": "站点名称精确匹配（仅 StationCode 为空时生效）",
            },
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "station_recount_paged": {
        "summary": "站点数据复测记录分页：复测任务与状态跟踪",
        "keywords": ["复测", "重测", "站点", "记录"],
        "route": "station_recount_paged",
        "returns": "复测记录分页列表（按下达时间倒序）",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "IssueTime": {
                "type": "datetime_list",
                "required": False,
                "desc": "下达时间范围 [开始, 结束]（闭区间，取列表首尾）",
            },
            "Status": {
                "type": "string",
                "required": False,
                "desc": "状态精确匹配；“待处理”或“未处理”会同时匹配两者，如“统计完成”",
            },
            "CountType": {
                "type": "string",
                "required": False,
                "enum": {"小时": "Hour", "日": "Day", "月": "Month"},
                "desc": "统计类型",
            },
            "DataType": {
                "type": "string",
                "required": False,
                "enum": {"原始": "Original", "审核": "Audited", "剔气象": "WeatherFiltered"},
                "desc": "数据类型",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "recount_report_templates": {
        "summary": "复测报告模板列表（内置+自定义）",
        "keywords": ["复测", "报告", "模板"],
        "route": "recount_report_templates",
        "returns": "报告模板列表",
        "params": {},
        "example": {},
    },
    "system_abnormal_reports": {
        "summary": "系统异常报告分页：超上下限标记(Mark=Y)的异常数据",
        "keywords": ["异常", "报告", "超限", "系统", "5分钟"],
        "route": "system_abnormal_reports",
        "returns": "异常数据分页列表",
        "params": {
            "StartTime": {"type": "datetime", "required": True, "desc": "开始时间"},
            "EndTime": {"type": "datetime", "required": True, "desc": "结束时间"},
            "Codes": {
                "type": "string_list",
                "required": False,
                "desc": "点位/区域编码列表；注意：留空时平台直接返回空页",
            },
            "PollutantCodes": {
                "type": "string_list",
                "required": False,
                "desc": "污染物编码列表",
            },
            "skipCount": {"type": "int", "required": False, "default": 0, "desc": "分页偏移"},
            "maxResultCount": {
                "type": "int",
                "required": False,
                "default": 20,
                "desc": "每页条数(1-1000)",
            },
        },
        "example": {
            "StartTime": "2026-07-01 00:00:00",
            "EndTime": "2026-07-02 00:00:00",
            "Codes": ["1737A"],
        },
    },
    "opa_organization": {
        "summary": "运维机构详情（按主键）",
        "keywords": ["运维", "机构", "详情"],
        "route": "opa_organization",
        "returns": "运维机构详情（含机构类型名）",
        "params": {"id": {"type": "int", "required": True, "desc": "机构主键"}},
        "example": {"id": 1},
    },
    "opa_organization_paged": {
        "summary": "运维机构分页：第三方运维单位名录",
        "keywords": ["运维", "机构", "单位", "名单"],
        "route": "opa_organization_paged",
        "returns": "运维机构分页列表（按创建时间倒序）",
        "params": {
            "OrgName": {"type": "string", "required": False, "desc": "机构名称模糊查询"},
            "OrgTypeId": {"type": "int", "required": False, "desc": "机构类型 Id 精确"},
            "AreaCode": {"type": "string", "required": False, "desc": "区域编码包含匹配"},
            "Status": {"type": "int", "required": False, "desc": "状态精确"},
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "opa_organization_types": {
        "summary": "运维机构类型字典列表",
        "keywords": ["运维", "机构", "类型", "字典"],
        "route": "opa_organization_types",
        "returns": "机构类型列表",
        "params": {},
        "example": {},
    },
    "opa_assessment": {
        "summary": "运维考核详情（按主键）",
        "keywords": ["运维", "考核", "详情"],
        "route": "opa_assessment",
        "returns": "考核详情（含机构名）",
        "params": {"id": {"type": "int", "required": True, "desc": "考核主键"}},
        "example": {"id": 1},
    },
    "opa_assessment_paged": {
        "summary": "运维考核分页：机构考核记录与周期",
        "keywords": ["运维", "考核", "评分", "机构"],
        "route": "opa_assessment_paged",
        "returns": "考核分页列表（按考核周期开始倒序）",
        "params": {
            "OrgId": {"type": "int", "required": False, "desc": "运维机构 Id 精确"},
            "AreaCode": {"type": "string", "required": False, "desc": "区域编码包含匹配"},
            "PeriodStartDate": {
                "type": "datetime",
                "required": False,
                "desc": "考核区间过滤开始（区间重叠语义）",
            },
            "PeriodEndDate": {
                "type": "datetime",
                "required": False,
                "desc": "考核区间过滤结束（区间重叠语义）",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "operation_flow_areas": {
        "summary": "运维流程可选区域列表（当前角色可见区县）",
        "keywords": ["运维", "流程", "区域", "区县"],
        "route": "operation_flow_areas",
        "returns": "区县编码/名称列表",
        "params": {},
        "example": {},
    },
    "operation_flow_design_paged": {
        "summary": "运维流程设计分页：流程模板/方案清单",
        "keywords": ["运维", "流程", "设计", "模板", "方案"],
        "route": "operation_flow_design_paged",
        "returns": "流程设计分页列表",
        "params": {
            "FlowName": {"type": "string", "required": False, "desc": "流程名称模糊查询"},
            "AreaId": {
                "type": "string",
                "required": False,
                "desc": "区县编码，多个逗号分隔；须在角色可见区域内",
            },
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "operation_flow_design_detail": {
        "summary": "运维流程设计详情（含节点定义）",
        "keywords": ["流程", "设计", "详情", "节点"],
        "route": "operation_flow_design_detail",
        "returns": "流程设计详情",
        "params": {"id": {"type": "int", "required": True, "desc": "流程设计主键"}},
        "example": {"id": 1},
    },
    "operation_flow_instance_paged": {
        "summary": "运维流程实例分页：工单执行记录",
        "keywords": ["运维", "流程", "实例", "工单", "执行"],
        "route": "operation_flow_instance_paged",
        "returns": "流程实例分页列表（按创建时间倒序）",
        "params": {
            "AreaCode": {
                "type": "string",
                "required": False,
                "desc": "区县编码，多个逗号分隔",
            },
            "StartTime": _OPT_START_TIME,
            "EndTime": _OPT_END_TIME,
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "operation_flow_instance_detail": {
        "summary": "运维流程实例详情（含处理日志与处理人）",
        "keywords": ["流程", "实例", "详情", "工单"],
        "route": "operation_flow_instance_detail",
        "returns": "流程实例详情",
        "params": {"id": {"type": "int", "required": True, "desc": "工单主键"}},
        "example": {"id": 1},
    },
    "work_order_paged": {
        "summary": "运维工单分页：按点位/时间/状态/类型查询工单",
        "keywords": ["工单", "运维", "任务", "检修"],
        "route": "work_order_paged",
        "returns": "工单分页列表",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "时间范围 [开始, 结束]（按创建时间过滤）",
            },
            "OrderStatus": {
                "type": "int_list",
                "required": False,
                "enum": {"待处理": 1, "处理中": 2, "待审核": 3, "已完成": 4},
                "desc": "工单状态集合",
            },
            "UrgencyType": {
                "type": "string_list",
                "required": False,
                "desc": "紧急程度集合，精确匹配",
            },
            "StatisticsType": {
                "type": "int_list",
                "required": False,
                "enum": {
                    "每日检查": 1,
                    "定期巡检": 2,
                    "数据异常检查": 3,
                    "每日自检": 4,
                    "现场声校准": 5,
                    "现场比对": 6,
                    "年度维护": 7,
                    "故障排查": 8,
                    "设备更换": 9,
                    "安防检查": 10,
                    "量值溯源": 12,
                },
                "desc": "工单类型集合；注意：留空时平台直接返回空列表",
            },
            **_PAGED_PARAMS,
        },
        "example": {
            "TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"],
            "StatisticsType": [8],
            "maxResultCount": 20,
        },
    },
    "fault_records": {
        "summary": "故障记录列表（全量，按时间升序）",
        "keywords": ["故障", "记录", "报修", "设备"],
        "route": "fault_records",
        "returns": "故障记录列表（全量，注意结果规模）",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "TimePoint": {
                "type": "datetime_list",
                "required": True,
                "desc": "时间范围 [开始, 结束]（按日期闭区间）",
            },
        },
        "example": {
            "Codes": ["1737A"],
            "TimePoint": ["2026-07-01 00:00:00", "2026-07-31 00:00:00"],
        },
    },
    "opa_attendance": {
        "summary": "运维考勤分页：站点签到记录",
        "keywords": ["考勤", "签到", "运维", "打卡"],
        "route": "opa_attendance",
        "returns": "考勤分页列表（按签到时间倒序）",
        "params": {
            "StationCodes": {
                "type": "string_list",
                "required": False,
                "desc": "点位编码列表",
            },
            "StartTime": _OPT_START_TIME,
            "EndTime": {"type": "datetime", "required": False, "desc": "结束时间(闭区间)"},
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "qc_arrange_list": {
        "summary": "远程质控安排列表：QC 下发任务与执行状态",
        "keywords": ["质控", "QC", "远程", "安排", "审核"],
        "route": "qc_arrange_list",
        "returns": "质控安排分页列表（按创建时间倒序）",
        "params": {
            "StationCode": {
                "type": "string",
                "required": False,
                "desc": "站点编码，逗号分隔；留空=全部角色可用站点",
            },
            "StartTime": {"type": "datetime", "required": True, "desc": "开始时间(含)"},
            "EndTime": {"type": "datetime", "required": True, "desc": "结束时间(开区间)"},
            **_PAGED_PARAMS,
        },
        "example": {
            "StartTime": "2026-07-01 00:00:00",
            "EndTime": "2026-07-02 00:00:00",
            "maxResultCount": 20,
        },
    },
    # —— 台账与字典 ——
    "noise_source_list": {
        "summary": "噪声源清单台账：登记的噪声源名录",
        "keywords": ["噪声源", "清单", "台账", "名录"],
        "route": "noise_source_list",
        "returns": "噪声源清单分页列表（按登记日期倒序）",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "TimePoint": {
                "type": "datetime_list",
                "required": False,
                "desc": "登记日期范围 [开始, 结束]（最多两个）",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "sensitive_areas": {
        "summary": "敏感集中区台账：噪声敏感区域汇聚点名录",
        "keywords": ["敏感", "集中区", "居住", "台账", "区域"],
        "route": "sensitive_areas",
        "returns": "敏感集中区分页列表（按纳入日期倒序）",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "TimePoint": {
                "type": "datetime_list",
                "required": False,
                "desc": "纳入日期范围 [开始, 结束]（最多两个）",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "quiet_city_daily": {
        "summary": "宁静城市日分析台账：逐日宁静城市建设分析记录",
        "keywords": ["宁静", "城市", "日报", "台账", "安静"],
        "route": "quiet_city_daily",
        "returns": "宁静城市日分析分页列表（按数据日期倒序）",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "TimePoint": {
                "type": "datetime_list",
                "required": False,
                "desc": "数据日期范围 [开始, 结束]（最多两个）",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "supervision_inspections": {
        "summary": "监督检查台账：监督执法/检查计划记录",
        "keywords": ["监督", "检查", "执法", "台账"],
        "route": "supervision_inspections",
        "returns": "监督检查分页列表（按计划检查时间倒序）",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "TimePoint": {
                "type": "datetime_list",
                "required": False,
                "desc": "计划检查时间范围 [开始, 结束]（最多两个）",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "horn_capture_records": {
        "summary": "喇叭抓拍台账：鸣笛抓拍记录（可按抓拍时间过滤）",
        "keywords": ["喇叭", "抓拍", "鸣笛", "台账"],
        "route": "horn_capture_records",
        "returns": "抓拍记录分页列表（按抓拍时间倒序）",
        "params": {
            "Codes": _CODES_OPTIONAL,
            "TimePoint": {
                "type": "datetime_list",
                "required": False,
                "desc": "抓拍时间范围 [开始, 结束]（最多两个）",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "event_strategy_list": {
        "summary": "噪声事件策略分页：事件预警判定策略配置",
        "keywords": ["事件", "策略", "预警", "配置"],
        "route": "event_strategy_list",
        "returns": "事件策略分页列表",
        "params": {
            "Name": {"type": "string", "required": False, "desc": "策略名称模糊查询"},
            "WarningLevel": {
                "type": "string",
                "required": False,
                "desc": "预警等级精确匹配",
            },
            **_PAGED_PARAMS,
        },
        "example": {"maxResultCount": 20},
    },
    "noise_limit_dict": {
        "summary": "噪声限值字典：GB3096 各功能区昼/夜限值标准",
        "keywords": ["限值", "标准", "GB3096", "功能区", "字典"],
        "route": "noise_limit_dict",
        "returns": "限值标准列表（达标判定依据）",
        "params": {},
        "example": {},
    },
    "station_properties": {
        "summary": "站点全量属性清单：全部站点的扩展属性数据",
        "keywords": ["站点", "属性", "清单", "全量"],
        "route": "station_properties",
        "returns": "站点属性列表（全量，注意结果规模）",
        "params": {
            "dataSource": {
                "type": "string",
                "required": False,
                "desc": "数据源标识（特殊值 hourDiffCheck 额外剔除部分因子）",
            },
        },
        "example": {},
    },
}


def catalog_api_names() -> list[str]:
    return list(API_CATALOG)


def score_apis(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """按关键词给目录打分（简化版 ZCode searchTools：词命中即计分）。"""
    tokens = [t for t in query.lower().split() if t]
    if not tokens:
        return []
    scored: list[tuple[int, str]] = []
    for name, entry in API_CATALOG.items():
        haystacks = " ".join(
            [name, entry.get("summary", ""), " ".join(entry.get("keywords", []))]
        ).lower()
        score = 0
        for token in tokens:
            if token in entry.get("keywords", []) or token == name:
                score += 10
            elif token in name:
                score += 6
            elif token in haystacks:
                score += 2
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"api": name, "summary": API_CATALOG[name]["summary"], "score": score}
        for score, name in scored[:max_results]
    ]
