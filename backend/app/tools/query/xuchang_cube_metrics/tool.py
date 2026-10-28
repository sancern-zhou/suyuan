"""许昌空气质量语义层查询工具（Cube Core REST / 127.0.0.1:4610）。

对接 xuchang-cube 语义层（projects/xuchang/data-ops/cube，Cube Core 0.35，
docker 宿主机部署）。Agent 传"度量+维度+时间范围"点数即可，不写 SQL——
指标口径唯一锁死在 schema/*.js 与采集 fetcher，同一问题永远同一个数。

口径一致性: 本文件 CATALOG 必须与 schema/*.js、采集 fetcher 三方保持一致
（采集: backend/app/fetchers/xuchang_henan_ssfb_publish.py、
xuchang_henan_ranking_recalc.py）。
查询走 JWT（CUBE_API_SECRET），连库侧为 cube_reader 只读账号，
无新增数据库权限。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from .quality_policy import quality_guidance
from .result_contract import validate_result
from .semantic_registry import cube_metadata

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# ---------------------------------------------------------------- 语义目录
# 单一事实源(本文件内): 结构化目录 → 渲染进工具描述。改口径时三处同步:
# fetchers(采集) ↔ cube/schema/*.js ↔ 此处。
CATALOG: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    # 城市小时排名：MySQL 窗口函数现算（实时），18 城市组同小时分区排名。
    # 排名规则与日/月一致：数值越低越靠前（Rank* 升序,1=最优），相同值并列。
    "SsfbCityHourRank": {
        "measures": [
            {"name": "rankAqi", "title": "AQI小时排名(升序,1=最优,含济源)"},
            {"name": "rankPm25", "title": "PM2.5小时排名(升序,1=最优)"},
            {"name": "rankPm10", "title": "PM10小时排名(升序,1=最优)"},
            {"name": "rankSo2", "title": "SO2小时排名(升序,1=最优)"},
            {"name": "rankNo2", "title": "NO2小时排名(升序,1=最优)"},
            {"name": "rankO3", "title": "O3小时排名(升序,1=最优)"},
            {"name": "rankCo", "title": "CO小时排名(升序,1=最优)"},
            {"name": "avgAqi", "title": "AQI"},
            {"name": "avgPm25", "title": "PM2.5(μg/m³)"},
            {"name": "avgPm10", "title": "PM10(μg/m³)"},
            {"name": "avgO3", "title": "O3(μg/m³)"},
            {"name": "avgNo2", "title": "NO2(μg/m³)"},
            {"name": "avgSo2", "title": "SO2(μg/m³)"},
            {"name": "avgCo", "title": "CO(mg/m³)"},
            {"name": "cityCount", "title": "参与排名城市数(应=18)"},
        ],
        "dimensions": [
            {"name": "city", "title": "城市名(含济源市)"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "groupId", "title": "城市组ID"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度,精确到小时)"},
        ],
    },
    # 乡镇站小时（中大国发平台口径，本地库，2025-2026 已回补完整）。
    # caliber 维度必须二选一过滤（app=审核 / src=原始），否则同站同时刻
    # 两条记录重复计数；官方结论优先 caliber='app'。数值已排除 -99 无效值。
    "TownHour": {
        "measures": [
            {"name": "count", "title": "小时记录数"},
            {"name": "avgPm25", "title": "PM2.5均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10均值(μg/m³)"},
            {"name": "avgSo2", "title": "SO2均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2均值(μg/m³)"},
            {"name": "avgCo", "title": "CO均值(mg/m³)"},
            {"name": "avgO3", "title": "O3均值(μg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
            {"name": "onlineSites", "title": "有数据站点数(去重)"},
        ],
        "dimensions": [
            {"name": "caliber", "title": "口径(app审核/src原始,必选其一过滤)"},
            {"name": "stationCode", "title": "乡镇站编码(平台内部,如1024B)"},
            {"name": "stationName", "title": "乡镇站名(前缀含区县,如建安区小召乡)"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度,2024-01-01起)"},
        ],
    },
    # 乡镇站日：本地库 2024-08 起且 2025 年起完整（2026-10 回补）。
    "TownDay": {
        "measures": [
            {"name": "count", "title": "站点日记录数"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
            {"name": "avgO3", "title": "O3日均(μg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
            {"name": "onlineSites", "title": "有数据站点数(去重)"},
        ],
        "dimensions": [
            {"name": "caliber", "title": "口径(app审核/src原始,必选其一过滤)"},
            {"name": "stationCode", "title": "乡镇站编码"},
            {"name": "stationName", "title": "乡镇站名(前缀含区县)"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataDate", "title": "数据日期(时间维度,src 2024-08-01起/app 2024-09-01起)"},
        ],
    },
    # 乡镇站 5 分钟：旧云平台替代源（TownStationData 2026-10-21 停更后启用），
    # 全部为原始（未审核）口径，仅保留最近 30 天；5 分钟不发布 AQI。
    "TownFiveMinute": {
        "measures": [
            {"name": "count", "title": "5分钟记录数"},
            {"name": "avgPm25", "title": "PM2.5(μg/m³)"},
            {"name": "avgPm10", "title": "PM10(μg/m³)"},
            {"name": "avgSo2", "title": "SO2(μg/m³)"},
            {"name": "avgNo2", "title": "NO2(μg/m³)"},
            {"name": "avgCo", "title": "CO(mg/m³)"},
            {"name": "avgO3", "title": "O3(μg/m³)"},
            {"name": "maxAqi", "title": "AQI(平台5分钟不发布,恒空)"},
            {"name": "onlineSites", "title": "有数据站点数(去重)"},
        ],
        "dimensions": [
            {"name": "stationCode", "title": "乡镇站编码(平台内部)"},
            {"name": "stationName", "title": "乡镇站名(前缀含区县)"},
            {"name": "countyName", "title": "区县名"},
            {"name": "dataTime", "title": "数据时间(时间维度,5分钟粒度,滚动30天)"},
        ],
    },
    # 城市小时: 18 城市组(含济源)逐小时六参数+AQI, 河南实时发布系统采集。
    "SsfbCityHour": {
        "measures": [
            {"name": "count", "title": "小时记录数"},
            {"name": "avgPm25", "title": "PM2.5均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10均值(μg/m³)"},
            {"name": "avgO3", "title": "O3均值(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2均值(μg/m³)"},
            {"name": "avgSo2", "title": "SO2均值(μg/m³)"},
            {"name": "avgCo", "title": "CO均值(mg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
        ],
        "dimensions": [
            {"name": "city", "title": "城市名(含济源市)"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "groupId", "title": "城市组ID"},
            {"name": "quality", "title": "空气质量等级(优/良...)"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度)"},
        ],
    },
    # 城市日: 唯一含济源的全量城市日数据源(2026-10-03 起)。
    # 源接口 2026-10 起日值不发布 PM10, avgPm10 可能为空。
    "SsfbCityDay": {
        "measures": [
            {"name": "count", "title": "日记录数"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(源10月起缺失,勿用于趋势)"},
            {"name": "avgO38h", "title": "O3-8h日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
        ],
        "dimensions": [
            {"name": "city", "title": "城市名(含济源市)"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "groupId", "title": "城市组ID"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataDate", "title": "数据日期(时间维度)"},
        ],
    },
    # 城市日排名：仅 periodType=daily（对官方发布日值升序排序，取原值不聚合）。
    # 月/年累计统计已改为官方月报口径，见 ProvinceMonth/ProvinceMonthCum；
    # 本表此前的 monthly/yearly 为本地手算，已停用并删除历史行（2026-10-16）。
    "SsfbCityRanking": {
        "measures": [
            {"name": "count", "title": "记录数"},
            {"name": "avgPm25", "title": "PM2.5(官方日值)"},
            {"name": "avgPm10", "title": "PM10(官方日值)"},
            {"name": "avgSo2", "title": "SO2(官方日值)"},
            {"name": "avgNo2", "title": "NO2(官方日值)"},
            {"name": "avgCo", "title": "CO(官方日值)"},
            {"name": "avgO38h", "title": "O3-8h(官方日值)"},
            {"name": "rankPm25", "title": "PM2.5日排名(升序,1=最优)"},
            {"name": "rankPm10", "title": "PM10日排名(升序,1=最优)"},
            {"name": "rankSo2", "title": "SO2日排名(升序,1=最优)"},
            {"name": "rankNo2", "title": "NO2日排名(升序,1=最优)"},
            {"name": "rankO3", "title": "O3日排名(升序,1=最优)"},
            {"name": "rankCo", "title": "CO日排名(升序,1=最优)"},
        ],
        "dimensions": [
            {"name": "periodType", "title": "期次类型(仅 daily)"},
            {"name": "period", "title": "期次(YYYY-MM-DD)"},
            {"name": "city", "title": "城市名(含济源市)"},
            {"name": "groupId", "title": "城市组ID"},
            {"name": "computedAt", "title": "计算时间(时间维度)"},
        ],
    },
    # 河南省环境空气质量月报官方附表（2025-12,2026-01~09 十期）。
    # Level=city 19市(区)含济源/航空港：城市月度及以上统计的唯一官方口径；
    # Level=district 88市辖区 / Level=county 101县市：无 O3(供暖季)/SO2/NO2/CO/重污染天。
    # 同比列 Xxx_YoY 为官方同比变化率(%)；区域数量随期次变化(85区/103县市→88区/101县市)。
    "ProvinceMonth": {
        "measures": [
            {"name": "pm10", "title": "PM10月均(μg/m³,官方)"},
            {"name": "pm10YoY", "title": "PM10同比变化率(%,官方)"},
            {"name": "pm25", "title": "PM2.5月均(μg/m³,官方)"},
            {"name": "pm25YoY", "title": "PM2.5同比变化率(%,官方)"},
            {"name": "o3", "title": "O3-8h第90百分位(μg/m³,供暖季期次无)"},
            {"name": "o3YoY", "title": "O3同比变化率(%)"},
            {"name": "goodDays", "title": "优良天数(当月)"},
            {"name": "goodDaysChange", "title": "优良天数同比变化(天)"},
            {"name": "goodDaysRatio", "title": "优良比例(%)"},
            {"name": "heavyDays", "title": "重度及以上污染天数(仅city级有)"},
            {"name": "heavyDaysChange", "title": "重度及以上污染天数同比变化(天)"},
            {"name": "compositeIndex", "title": "综合指数(官方)"},
            {"name": "compositeIndexYoY", "title": "综合指数同比变化率(%)"},
            {"name": "count", "title": "记录数"},
        ],
        "dimensions": [
            {"name": "level", "title": "层级(city=19市(区)/district=88市辖区/county=101县市/province=全省)"},
            {"name": "city", "title": "所属省辖市(市级行=市全称;全省行=全省)"},
            {"name": "region", "title": "区域名(市全称/区/县市)"},
            {"name": "dataMonth", "title": "月份(时间维度,2025-12/2026-01~09)"},
        ],
    },
    # 同上，1-N月累计（截至该月）。
    "ProvinceMonthCum": {
        "measures": [
            {"name": "pm10", "title": "PM10累计均值(μg/m³,官方)"},
            {"name": "pm10YoY", "title": "PM10累计同比变化率(%)"},
            {"name": "pm25", "title": "PM2.5累计均值(μg/m³,官方)"},
            {"name": "pm25YoY", "title": "PM2.5累计同比变化率(%)"},
            {"name": "o3", "title": "O3-8h第90百分位(累计,供暖季期次无)"},
            {"name": "o3YoY", "title": "O3累计同比变化率(%)"},
            {"name": "goodDays", "title": "优良天数(1-N月累计)"},
            {"name": "goodDaysChange", "title": "优良天数累计同比变化(天)"},
            {"name": "goodDaysRatio", "title": "优良比例(累计,%)"},
            {"name": "heavyDays", "title": "重度及以上污染天数(累计,仅city级有)"},
            {"name": "heavyDaysChange", "title": "重度及以上污染天数累计同比变化(天)"},
            {"name": "compositeIndex", "title": "综合指数(累计,官方)"},
            {"name": "compositeIndexYoY", "title": "综合指数累计同比变化率(%)"},
            {"name": "count", "title": "记录数"},
        ],
        "dimensions": [
            {"name": "level", "title": "层级(city/district/county/province)"},
            {"name": "city", "title": "所属省辖市"},
            {"name": "region", "title": "区域名(市全称/区/县市)"},
            {"name": "dataMonth", "title": "累计截止月(时间维度,如2026-09=1-9月累计)"},
        ],
    },
    # 许昌县市区官方月报统计（剔除沙尘,2020-01~2026-09,官方月报原值,非明细聚合）。
    # 2020 年数值取自 2021 年月报"上年同期"列;重污染天 2023 起才有;
    # 累计表与当月表个别区域存在 1~2 天官方修订差(原值入库,勿互相换算)。
    "CountyMonth": {
        "measures": [
            {"name": "pm10", "title": "PM10月均(μg/m³)"},
            {"name": "pm25", "title": "PM2.5月均(μg/m³)"},
            {"name": "so2", "title": "SO2月均(μg/m³)"},
            {"name": "no2", "title": "NO2月均(μg/m³)"},
            {"name": "co95", "title": "CO第95百分位月值(mg/m³)"},
            {"name": "o3_8h_90", "title": "O3-8h第90百分位月值(μg/m³)"},
            {"name": "goodDays", "title": "优良天数(当月)"},
            {"name": "heavyDays", "title": "重污染天数(当月,2023起才有)"},
            {"name": "compositeIndex", "title": "综合指数(当月)"},
            {"name": "count", "title": "记录数"},
        ],
        "dimensions": [
            {"name": "region", "title": "区域(许昌市/魏都区/开发区/东城区/示范区/建安区/鄢陵县/襄城县/禹州市/长葛市)"},
            {"name": "regionType", "title": "区域类型(city=全市/urban=市辖区国家平台/county=县市省平台)"},
            {"name": "dataMonth", "title": "月份(时间维度,2020-01~2026-09)"},
        ],
    },
    # 同上,1-N月累计(YTD): 优良天/重污染天为期间合计,浓度为期间平均。
    "CountyMonthCum": {
        "measures": [
            {"name": "pm10", "title": "PM10累计均值(μg/m³)"},
            {"name": "pm25", "title": "PM2.5累计均值(μg/m³)"},
            {"name": "so2", "title": "SO2累计均值(μg/m³)"},
            {"name": "no2", "title": "NO2累计均值(μg/m³)"},
            {"name": "co95", "title": "CO第95百分位累计值(mg/m³)"},
            {"name": "o3_8h_90", "title": "O3-8h第90百分位累计值(μg/m³)"},
            {"name": "goodDays", "title": "优良天数(1-N月合计)"},
            {"name": "heavyDays", "title": "重污染天数(1-N月合计,2023起才有)"},
            {"name": "compositeIndex", "title": "综合指数(1-N月累计)"},
            {"name": "count", "title": "记录数"},
        ],
        "dimensions": [
            {"name": "region", "title": "区域(许昌市/魏都区/开发区/东城区/示范区/建安区/鄢陵县/襄城县/禹州市/长葛市)"},
            {"name": "regionType", "title": "区域类型(city=全市/urban=市辖区国家平台/county=县市省平台)"},
            {"name": "periodEnd", "title": "累计截止月(时间维度,取月末,如2026-09-30=1-9月累计)"},
        ],
    },
    # 全省区县站点小时(两根树 193 区县,剔除国控;County 字段为区县归属): 站点目录见
    # xuchang_station_catalog 与 SsfbDimSite, 编码为河南实时发布系统数字编码(SiteID)。
    # 平台仅发布省控站数据(约241个), 市控站挂树无数据。
    "SsfbSiteHour": {
        "measures": [
            {"name": "count", "title": "小时记录数"},
            {"name": "avgPm25", "title": "PM2.5均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10均值(μg/m³)"},
            {"name": "avgO3", "title": "O3均值(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2均值(μg/m³)"},
            {"name": "avgSo2", "title": "SO2均值(μg/m³)"},
            {"name": "avgCo", "title": "CO均值(mg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
            {"name": "onlineSites", "title": "有数据站点数(去重)"},
        ],
        "dimensions": [
            {"name": "siteId", "title": "县级站编码(SiteID)"},
            {"name": "siteName", "title": "站点名"},
            {"name": "onlineType", "title": "站点类别(县级市控SK/县级省控SCK)"},
            {"name": "city", "title": "所属城市"},
            {"name": "county", "title": "归属区县(区县口径按此分组)"},
            {"name": "area", "title": "源平台区域"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度)"},
        ],
    },
    # 全省区县站点日值: 仅单日接口, 历史按日累积。
    "SsfbSiteDay": {
        "measures": [
            {"name": "count", "title": "站点日记录数"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
            {"name": "onlineSites", "title": "有数据站点数(去重)"},
        ],
        "dimensions": [
            {"name": "siteId", "title": "县级站编码(SiteID)"},
            {"name": "siteName", "title": "站点名"},
            {"name": "onlineType", "title": "站点类别"},
            {"name": "city", "title": "所属城市"},
            {"name": "county", "title": "归属区县"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "dataDate", "title": "数据日期(时间维度)"},
        ],
    },
    # 全省区县小时/日(190区县,含济源与功能区,与平台"区县"页签同源)。
    "SsfbCountyHour": {
        "measures": [
            {"name": "count", "title": "小时记录数"},
            {"name": "avgPm25", "title": "PM2.5均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10均值(μg/m³)"},
            {"name": "avgO3", "title": "O3均值(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2均值(μg/m³)"},
            {"name": "avgSo2", "title": "SO2均值(μg/m³)"},
            {"name": "avgCo", "title": "CO均值(mg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
            {"name": "onlineCounties", "title": "有数据区县数(去重)"},
        ],
        "dimensions": [
            {"name": "county", "title": "区县名(含济源市/功能区)"},
            {"name": "city", "title": "所属省辖市"},
            {"name": "cityCode", "title": "区县行政区码"},
            {"name": "groupId", "title": "区县组ID"},
            {"name": "quality", "title": "空气质量等级(优/良...)"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度)"},
        ],
    },
    "SsfbCountyDay": {
        "measures": [
            {"name": "count", "title": "日记录数"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
            {"name": "onlineCounties", "title": "有数据区县数(去重)"},
        ],
        "dimensions": [
            {"name": "county", "title": "区县名(含济源市/功能区)"},
            {"name": "city", "title": "所属省辖市"},
            {"name": "cityCode", "title": "区县行政区码"},
            {"name": "groupId", "title": "区县组ID"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataDate", "title": "数据日期(时间维度)"},
        ],
    },
    # 区县小时排名：窗口函数现算（实时），190 区县同小时分区排名。
    # 排名规则与城市/日粒度一致：数值越低越靠前（升序），相同值并列。
    "SsfbCountyHourRank": {
        "measures": [
            {"name": "rankAqi", "title": "AQI小时排名(升序,1=最优,含济源)"},
            {"name": "rankPm25", "title": "PM2.5小时排名(升序,1=最优)"},
            {"name": "rankPm10", "title": "PM10小时排名(升序,1=最优)"},
            {"name": "rankO3", "title": "O3小时排名(升序,1=最优)"},
            {"name": "rankNo2", "title": "NO2小时排名(升序,1=最优)"},
            {"name": "rankSo2", "title": "SO2小时排名(升序,1=最优)"},
            {"name": "rankCo", "title": "CO小时排名(升序,1=最优)"},
            {"name": "avgAqi", "title": "AQI"},
            {"name": "avgPm25", "title": "PM2.5(μg/m³)"},
            {"name": "avgPm10", "title": "PM10(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h(μg/m³)"},
            {"name": "avgNo2", "title": "NO2(μg/m³)"},
            {"name": "avgSo2", "title": "SO2(μg/m³)"},
            {"name": "avgCo", "title": "CO(mg/m³)"},
            {"name": "countyCount", "title": "参与排名区县数"},
        ],
        "dimensions": [
            {"name": "county", "title": "区县名"},
            {"name": "city", "title": "所属省辖市"},
            {"name": "groupId", "title": "区县组ID"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度,精确到小时)"},
        ],
    },
    # 区县日排名：与平台"区县排名"完全同口径（升序并列,平台O3列=O3-8H）。
    "SsfbCountyDayRank": {
        "measures": [
            {"name": "rankAqi", "title": "AQI日排名(升序,1=最优,含济源)"},
            {"name": "rankPm25", "title": "PM2.5日排名(升序,1=最优)"},
            {"name": "rankPm10", "title": "PM10日排名(升序,1=最优)"},
            {"name": "rankO3", "title": "O3-8h日排名(升序,1=最优,平台O3列)"},
            {"name": "rankNo2", "title": "NO2日排名(升序,1=最优)"},
            {"name": "rankSo2", "title": "SO2日排名(升序,1=最优)"},
            {"name": "rankCo", "title": "CO日排名(升序,1=最优)"},
            {"name": "avgAqi", "title": "AQI"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
            {"name": "countyCount", "title": "参与排名区县数(应≈188)"},
        ],
        "dimensions": [
            {"name": "county", "title": "区县名"},
            {"name": "city", "title": "所属省辖市"},
            {"name": "groupId", "title": "区县组ID"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataDate", "title": "数据日期(时间维度)"},
        ],
    },
    # 站点小时/日排名：窗口函数现算（实时，省控站约241个有数据）。
    "SsfbSiteHourRank": {
        "measures": [
            {"name": "rankAqi", "title": "AQI小时排名(升序,1=最优)"},
            {"name": "rankPm25", "title": "PM2.5小时排名(升序,1=最优)"},
            {"name": "rankPm10", "title": "PM10小时排名(升序,1=最优)"},
            {"name": "rankO3", "title": "O3小时排名(升序,1=最优)"},
            {"name": "rankNo2", "title": "NO2小时排名(升序,1=最优)"},
            {"name": "rankSo2", "title": "SO2小时排名(升序,1=最优)"},
            {"name": "rankCo", "title": "CO小时排名(升序,1=最优)"},
            {"name": "avgAqi", "title": "AQI"},
            {"name": "avgPm25", "title": "PM2.5(μg/m³)"},
            {"name": "siteCount", "title": "参与排名站点数"},
        ],
        "dimensions": [
            {"name": "siteId", "title": "站点编码(SiteID)"},
            {"name": "siteName", "title": "站点名"},
            {"name": "city", "title": "所属城市"},
            {"name": "county", "title": "归属区县"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度,精确到小时)"},
        ],
    },
    "SsfbSiteDayRank": {
        "measures": [
            {"name": "rankAqi", "title": "AQI日排名(升序,1=最优)"},
            {"name": "rankPm25", "title": "PM2.5日排名(升序,1=最优)"},
            {"name": "rankPm10", "title": "PM10日排名(升序,1=最优)"},
            {"name": "rankO3", "title": "O3-8h日排名(升序,1=最优)"},
            {"name": "rankNo2", "title": "NO2日排名(升序,1=最优)"},
            {"name": "rankSo2", "title": "SO2日排名(升序,1=最优)"},
            {"name": "rankCo", "title": "CO日排名(升序,1=最优)"},
            {"name": "avgAqi", "title": "AQI"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "siteCount", "title": "参与排名站点数"},
        ],
        "dimensions": [
            {"name": "siteId", "title": "站点编码(SiteID)"},
            {"name": "siteName", "title": "站点名"},
            {"name": "city", "title": "所属城市"},
            {"name": "county", "title": "归属区县"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataDate", "title": "数据日期(时间维度)"},
        ],
    },
    # 许昌市年度目标 vs 实际（官方定版,2015-2026,《00重要基础数据.zip》01表回补,无自动采集）。
    # 目标值全库唯一;实际值为国家网考核口径,与 CityYearPm25Avg 的实时未审核列有 1~5 μg 差,
    # 年度考核问题一律以本 Cube 为准。
    "XuchangCityYearTarget": {
        "measures": [
            {"name": "pm10Target", "title": "PM10年度目标(μg/m³)"},
            {"name": "pm25Target", "title": "PM2.5年度目标(μg/m³)"},
            {"name": "goodDaysTarget", "title": "优良天年度目标(天)"},
            {"name": "heavyDaysTarget", "title": "重污染天年度目标(天,2022起下达)"},
            {"name": "pm10", "title": "PM10年均实际(μg/m³,国家网口径)"},
            {"name": "pm25", "title": "PM2.5年均实际(μg/m³,国家网口径)"},
            {"name": "so2", "title": "SO2年均(μg/m³,仅2015-2025)"},
            {"name": "no2", "title": "NO2年均(μg/m³)"},
            {"name": "co95", "title": "CO第95百分位年均(mg/m³)"},
            {"name": "o3", "title": "O3年均(μg/m³,仅2015-2020)"},
            {"name": "goodDays", "title": "优良天实际(天)"},
            {"name": "heavyDays", "title": "重污染天实际(天,剔沙尘)"},
            {"name": "o3ExceedDays", "title": "臭氧超标天(天)"},
            {"name": "count", "title": "记录数(应=1/年)"},
        ],
        "dimensions": [
            {"name": "year", "title": "年度(2015-2026,过滤 year equals 2023)"},
            {"name": "remark", "title": "口径备注(如2025市定目标)"},
        ],
    },
    # 许昌县市区年度目标 vs 实际（官方考核定版剔沙尘,2020-2025,05表+剔沙尘表回补）。
    # 年度考核口径与 CountyMonth 月报的区别: 2023 年重污染天差 3~4 天(2023-03 沙尘,
    # 月报未剔沙尘),年度考核一律用本 Cube;2020 年仅重污染天。
    "XuchangCountyYearTarget": {
        "measures": [
            {"name": "pm10Target", "title": "PM10年度目标(μg/m³)"},
            {"name": "pm10", "title": "PM10年均实际(μg/m³)"},
            {"name": "pm25Target", "title": "PM2.5年度目标(μg/m³)"},
            {"name": "pm25", "title": "PM2.5年均实际(μg/m³)"},
            {"name": "goodDaysTarget", "title": "优良天年度目标(天)"},
            {"name": "goodDays", "title": "优良天实际(天)"},
            {"name": "heavyDaysTarget", "title": "重污染天年度目标(天,2022起)"},
            {"name": "heavyDays", "title": "重污染天实际(天,剔沙尘)"},
            {"name": "count", "title": "记录数(应=1/区域/年)"},
        ],
        "dimensions": [
            {"name": "region", "title": "区域(许昌市/魏都区/开发区/东城区/示范区/建安区/鄢陵县/襄城县/禹州市/长葛市)"},
            {"name": "regionType", "title": "区域类型(city=全市/urban=市辖区国家平台/county=县市省平台)"},
            {"name": "year", "title": "年度(2020-2025)"},
            {"name": "pm10Completed", "title": "PM10目标完成(是/否)"},
            {"name": "pm25Completed", "title": "PM2.5目标完成(是/否)"},
            {"name": "goodDaysCompleted", "title": "优良天目标完成(是/否)"},
            {"name": "heavyDaysCompleted", "title": "重污染天目标完成(是/否)"},
            {"name": "remark", "title": "口径备注"},
        ],
    },
    # 河南 18 地市年度目标完成情况（省考核口径,2021-2025,03表回补）。
    # 优良天/重污染天 2021/2022/2024 为天数、2023/2025 为比例%(Ratio列);
    # 5-9月臭氧超标天仅 2022-2023;2025 行未定稿(Remark 注明)。
    "HenanCityYearTarget": {
        "measures": [
            {"name": "pm10Target", "title": "PM10年度目标(μg/m³)"},
            {"name": "pm10", "title": "PM10年均实际(μg/m³,省考核)"},
            {"name": "pm25Target", "title": "PM2.5年度目标(μg/m³)"},
            {"name": "pm25", "title": "PM2.5年均实际(μg/m³,省考核)"},
            {"name": "goodDaysTarget", "title": "优良天目标(天,2021/2022/2024)"},
            {"name": "goodDays", "title": "优良天实际(天,2021/2022/2024)"},
            {"name": "goodDaysRatioTarget", "title": "优良天比例目标(%)"},
            {"name": "goodDaysRatio", "title": "优良天比例实际(%,2023/2025)"},
            {"name": "heavyDaysTarget", "title": "重污染天目标(天)"},
            {"name": "heavyDays", "title": "重污染天实际(天)"},
            {"name": "heavyDaysRatioTarget", "title": "重污染天比例目标(%)"},
            {"name": "heavyDaysRatio", "title": "重污染天比例实际(%,2023/2025)"},
            {"name": "o3ExceedDaysTarget", "title": "5-9月臭氧超标天目标(天,仅2022-2023)"},
            {"name": "o3ExceedDays", "title": "5-9月臭氧超标天实际(天)"},
            {"name": "o3ExceedOver", "title": "臭氧超标天超出目标(天)"},
            {"name": "completedCount", "title": "完成指标数量(0-4)"},
            {"name": "count", "title": "记录数(应=18/年)"},
        ],
        "dimensions": [
            {"name": "city", "title": "地市(18个含济源市)"},
            {"name": "year", "title": "年度(2021-2025)"},
            {"name": "pm10Completed", "title": "PM10目标完成(是/否)"},
            {"name": "pm25Completed", "title": "PM2.5目标完成(是/否)"},
            {"name": "goodDaysCompleted", "title": "优良天目标完成(是/否)"},
            {"name": "heavyDaysCompleted", "title": "重污染天目标完成(是/否)"},
            {"name": "remark", "title": "口径备注(如省/市口径差)"},
        ],
    },
    # 生态环境部 168 重点城市排名（2026-01~07 逐月+累计,部发布值,无自动采集）。
    # 仅用于全国排名与横向对比;许昌浓度绝对值用本地口径 Cube。
    "Rank168CityMonthly": {
        "measures": [
            {"name": "compositeIndex", "title": "环境空气质量综合指数(部发布)"},
            {"name": "compositeIndexRank", "title": "综合指数排名(倒序,1=最差)"},
            {"name": "pm25", "title": "PM2.5浓度(μg/m³,部发布)"},
            {"name": "pm25Rank", "title": "PM2.5浓度排名(倒序,1=最差)"},
            {"name": "count", "title": "记录数"},
        ],
        "dimensions": [
            {"name": "city", "title": "城市(168重点城市)"},
            {"name": "periodType", "title": "期次类型(month当月/cum累计,必选其一过滤)"},
            {"name": "periodLabel", "title": "期次标签(1月/1-7月)"},
            {"name": "dataMonth", "title": "月份(时间维度,当月行=当月/累计行=截止月)"},
            {"name": "periodEnd", "title": "累计截止月(时间维度,仅累计行)"},
        ],
    },
}

ALLOWED_FILTER_OPERATORS = {
    "equals", "notEquals", "contains", "notContains", "in", "notIn",
    "afterDate", "beforeDate", "afterOrOnDate", "beforeOrOnDate",
    "set", "notSet",
}

DATA_WINDOW_NOTE = "数据窗口: 2026-10-03 起(源平台仅保留约8天滚动+每日累积);"


def _render_guide() -> str:
    lines = ["", "【语义目录】(成员名 = Cube.成员; 浓度单位 μg/m³,CO 为 mg/m³)"]
    for cube, parts in CATALOG.items():
        lines.append(f"\n■ {cube}")
        lines.append("  度量(measures): " + "; ".join(
            f"{m['name']}={m['title']}" for m in parts["measures"]))
        lines.append("  维度(dimensions): " + "; ".join(
            f"{d['name']}={d['title']}" for d in parts["dimensions"]))
    lines.append("")
    lines.append(
        DATA_WINDOW_NOTE
        + "排名类问题按对象选 Cube: 城市日排名用 SsfbCityRanking(仅 periodType=daily,官方日值升序);"
        "城市/区/县市的月/年累计官方统计用 ProvinceMonth/ProvinceMonthCum"
        "(河南省环境空气质量月报,Level=city 为 19 市(区)含济源/航空港、district 为 88 市辖区、county 为 101 县市;"
        "覆盖 2025-12 与 2026-01~09 共十期,供暖季期次无 O3 列,区/县表无 SO2/NO2/CO/重污染天;"
        "同比列 Xxx_YoY 是官方同比变化率,不是上年绝对值;当月查 ProvinceMonth 过滤 dataMonth,"
        "年/YTD 累计查 ProvinceMonthCum 过滤 dataMonth;这是城市月度及以上的唯一官方口径);"
        "SsfbCityRanking 的 monthly/yearly 为本地手算口径,已停用、历史行已删除,不要再引用;"
        "SsfbCityDay 等城市日 Cube 只用于逐日明细与序列查询,不要用 granularity=month/year "
        "或任何方式把日值汇成月度及以上统计——许昌市月度及以上统计走 airdata_calc_report_summary 报表接口"
        "或 ProvinceMonth 官方值;"
        "区县排名用 SsfbCountyDayRank/SsfbCountyHourRank(与省平台'区县排名'同口径,190区县含济源,升序并列);"
        "站点排名用 SsfbSiteDayRank/SsfbSiteHourRank(省控站约241个,本系统统一口径);"
        "许昌县市区(10区域)官方月度统计与年/YTD累计用 CountyMonth/CountyMonthCum"
        "(2020-01~2026-09官方月报原值,剔除沙尘;当月查 CountyMonth 过滤 dataMonth,"
        "累计查 CountyMonthCum 过滤 periodEnd;重污染天2023起才有;"
        "这是官方发布统计,优先于任何由明细自算的县市区月度值);"
        "年度目标与完成情况查年度定版 Cube: 许昌市用 XuchangCityYearTarget(2015-2026,"
        "目标值唯一来源,实际值为国家网考核口径),许昌县市区用 XuchangCountyYearTarget"
        "(2020-2025,剔沙尘考核定版;2023年重污染天与月报差3~4天系2023-03沙尘,年度口径以本表为准),"
        "河南18地市用 HenanCityYearTarget(2021-2025,省考核;优良天/重污染天2021/2022/2024为天数、"
        "2023/2025为比例%,2025行未定稿);168城市全国排名用 Rank168CityMonthly"
        "(2026-01~07,过滤 periodType=month/cum,仅用于全国排名,浓度绝对值用本地口径);"
        "小时排名过滤 dataTime 到具体小时,日排名过滤 dataDate 到具体日期;"
        "排名规则统一为数值越低越靠前(Rank*=1 最优),相同值并列(RANK:1,2,2,4);"
        "乡镇站(76个,2024起)小时/日用 TownHour/TownDay,必须过滤 caliber(app=审核,官方结论优先),"
        "否则原始与审核重复计数;"
        "审核口径(caliber='app')常滞后甚至断档,查最新时段发现 app 无数据或覆盖不足时,"
        "回退 caliber='src' 查原始口径,并在答复中注明为未审核原始数据;"
        "乡镇站最近30天内的 5 分钟实时数据用 TownFiveMinute"
        "(旧云平台替代源,全部为原始未审核口径,平台不发布 5 分钟 AQI,"
        "AQI/等级需按 HJ633 由六参数推算并注明为推算值;乡镇小时/日历史仍以 TownHour/TownDay 为准)。"
    )
    return "\n".join(lines)


def _make_token(secret: str, ttl_seconds: int = 300) -> str:
    """HS256 JWT（Cube API_SECRET 鉴权, 短时效, 每次调用现签）。"""
    def b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps({"exp": int(time.time()) + ttl_seconds}).encode())
    signature = b64url(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{signature}"


async def cube_load(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """执行一次 Cube Core /load 查询，返回解包 value 后的扁平行。

    工具执行路径（XuchangCubeMetricsTool.execute）与大屏快照 fetcher
    共用此入口，鉴权、排队等待与错误语义只维护一份。
    """
    base_url = os.getenv("CUBE_API_URL", "http://127.0.0.1:4610/cubejs-api/v1")
    secret = os.getenv("CUBE_API_SECRET", "")
    if not secret:
        raise RuntimeError("CUBE_API_SECRET 未配置(语义层鉴权)")

    token = _make_token(secret)
    wait_seconds = float(os.getenv("CUBE_API_WAIT_SECONDS", "60"))
    started = time.monotonic()
    deadline = started + wait_seconds
    body: Dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.post(
                f"{base_url}/load",
                json={"query": query},
                headers={"Authorization": token},
            )
            if resp.status_code != 200:
                detail = resp.text[:500]
                raise RuntimeError(f"语义层返回 {resp.status_code}: {detail}")
            body = resp.json()
            pending = str(body.get("error") or "")
            if "continue wait" not in pending.lower():
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"语义层查询排队超时({round(time.monotonic() - started, 1)}s): {pending}"
                )
            await asyncio.sleep(1.5)
    if body.get("error"):
        raise RuntimeError(f"语义层错误: {body['error']}")

    return [
        {k: (v.get("value") if isinstance(v, dict) else v)
         for k, v in row.items()}
        for row in body.get("data", [])
    ]


class XuchangCubeMetricsTool(LLMTool):
    """经语义层查询许昌空气质量指标（口径唯一,免写SQL）。"""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 1000

    def __init__(self):
        self.tool_name = "xuchang_cube_metrics"
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询许昌本地空气质量指标(语义层,口径唯一):河南18城市组(含济源)小时/日"
                "六参数与AQI、城市/区县/站点的小时与日排名(数值越低排名越靠前,相同值并列,"
                "区县排名与省平台同口径)、全省区县(190个含济源)小时/日数据、"
                "许昌县级站小时/日数据、乡镇站(76个)小时/日数据(2024起,审核/原始口径二选一)、"
                "许昌县市区官方月度统计(2020-01~2026-09,剔除沙尘,CountyMonth/CountyMonthCum)、"
                "河南省官方月报统计(19市/88市辖区/101县市,ProvinceMonth/ProvinceMonthCum)、"
                "年度目标完成情况(许昌市 XuchangCityYearTarget 2015-2026/许昌县市区 "
                "XuchangCountyYearTarget 2020-2025/河南18地市 HenanCityYearTarget 2021-2025)、"
                "168重点城市全国排名(Rank168CityMonthly,2026年1-7月)。"
                "传 measures+dimensions+时间范围即可,不需要写SQL;"
                "城市日排名用 SsfbCityRanking(仅 periodType=daily);"
                "城市/区/县市的月与1-N月累计官方统计用 ProvinceMonth/ProvinceMonthCum(过滤 level);"
                "县市区月度及1-N月累计统计用 CountyMonth/CountyMonthCum(官方月报口径);"
                "年度目标与完成情况用 XuchangCityYearTarget/XuchangCountyYearTarget/HenanCityYearTarget(过滤 year);"
                "168城市全国排名用 Rank168CityMonthly(过滤 periodType);"
                "区县排名用 SsfbCountyDayRank/SsfbCountyHourRank,站点排名用 SsfbSiteDayRank/SsfbSiteHourRank;"
                "乡镇站问题用 TownHour/TownDay 并过滤 caliber(官方结论用 app;"
                "app 无最新时段数据时回退 src 并注明为未审核原始数据);"
                "乡镇站最近30天 5 分钟实时数据用 TownFiveMinute(原始未审核,AQI需按HJ633推算)。"
                + _render_guide()
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measures": {
                        "type": "array", "items": {"type": "string"},
                        "description": "度量成员,如 ['SsfbCityRanking.rankPm25','SsfbCityRanking.avgPm25'],须同一Cube",
                    },
                    "describe_cube": {
                        "type": "string",
                        "description": "(可选)只查询某个Cube的指标定义、粒度和适用范围，不执行数据查询",
                    },
                    "dimensions": {
                        "type": "array", "items": {"type": "string"},
                        "description": "(可选)分组维度,如 ['SsfbCityRanking.city']",
                    },
                    "time_dimension": {
                        "type": "string",
                        "description": "(可选)时间维度成员,如 'SsfbCityHour.dataTime'",
                    },
                    "date_range": {
                        "description": "(可选)'last 7 days'等关键字,或 ['2026-10-03','2026-10-09']",
                    },
                    "granularity": {
                        "type": "string", "enum": ["hour", "day", "week", "month", "year"],
                        "description": "(可选)时间粒度,给趋势序列时用",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "member": {"type": "string"},
                                "operator": {"type": "string"},
                                "values": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["member", "operator"],
                        },
                        "description": "(可选)过滤条件,如 SsfbCityRanking.period equals 2026-10、SsfbCityHour.city in [济源市,许昌市]",
                    },
                    "order": {
                        "type": "object",
                        "description": "(可选)排序,如 {'SsfbCityRanking.rankPm25':'asc'}",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回行数上限(默认50,最大1000)",
                        "default": 50,
                    },
                },
                "required": [],
            },
        }
        super().__init__(
            name=self.tool_name,
            description="查询许昌空气质量指标(语义层REST,口径唯一,免SQL,含济源排名)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    # ------------------------------------------------------------ 校验
    def _member_cube(self, member: str, kind: str) -> Optional[str]:
        if "." not in member:
            return None
        cube, name = member.split(".", 1)
        part = CATALOG.get(cube)
        if not part:
            return None
        key = "measures" if kind == "measure" else "dimensions"
        if name not in {m["name"] for m in part[key]}:
            return None
        return cube

    def _validate(self, measures, dimensions, time_dimension, filters):
        if not measures:
            return None, "measures 不能为空"
        cubes = set()
        for m in measures:
            c = self._member_cube(m, "measure")
            if c is None:
                return None, f"未知度量 {m}(不在语义目录中)"
            cubes.add(c)
        for d in dimensions or []:
            c = self._member_cube(d, "dimension")
            if c is None:
                return None, f"未知维度 {d}(不在语义目录中)"
            cubes.add(c)
        if time_dimension:
            c = self._member_cube(time_dimension, "dimension")
            if c is None:
                return None, f"未知时间维度 {time_dimension}"
            cubes.add(c)
        for f in filters or []:
            member = str(f.get("member", ""))
            c = self._member_cube(member, "dimension")
            if c is None:
                return None, f"过滤条件成员未知或不是维度: {member}"
            if f.get("operator") not in ALLOWED_FILTER_OPERATORS:
                return None, f"不支持的过滤操作符: {f.get('operator')}"
            cubes.add(c)
        if len(cubes) > 1:
            return None, f"一次查询只能用一个 Cube 的成员,当前跨了: {sorted(cubes)}"
        cube = cubes.pop()
        if cube in {"TownHour", "TownDay"}:
            caliber_filters = [
                f for f in filters or []
                if f.get("member") == f"{cube}.caliber"
            ]
            if not caliber_filters:
                return None, f"{cube} 必须明确过滤 caliber=app 或 caliber=src，避免原始与审核口径重复计数"
            values = {
                str(value) for item in caliber_filters for value in (item.get("values") or [])
            }
            if not values.intersection({"app", "src"}):
                return None, f"{cube}.caliber 只能使用 app 或 src"
        return cube, None

    # ------------------------------------------------------------ 执行
    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        measures: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
        time_dimension: Optional[str] = None,
        date_range: Any = None,
        granularity: Optional[str] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        order: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        describe_cube: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if describe_cube:
            if describe_cube not in CATALOG:
                return {"success": False, "summary": f"未知 Cube: {describe_cube}。允许: {', '.join(CATALOG)}"}
            semantic = cube_metadata(describe_cube, CATALOG)
            payload = {
                "success": True,
                "cube": describe_cube,
                "semantic_context": {
                    "registry_version": semantic.get("registry_version", 0),
                    "dataset": semantic.get("dataset"),
                    "grain": semantic.get("grain"),
                    "applicability": semantic.get("applicability"),
                    "source_window": semantic.get("source_window"),
                    "limitations": semantic.get("limitations", []),
                    "metric_definitions": semantic.get("measures", {}),
                },
                "summary": f"{describe_cube} 指标定义（registry v{semantic.get('registry_version', 0)}）",
            }
            contract_errors = validate_result("metric_definition", payload)
            if contract_errors:
                logger.warning("xuchang_metric_definition_contract_violation", errors=contract_errors)
            return payload
        cube, err = self._validate(measures, dimensions, time_dimension, filters)
        if err:
            return {"success": False, "data": None, "summary": f"参数校验失败: {err}"}

        query: Dict[str, Any] = {"measures": measures}
        if dimensions:
            query["dimensions"] = dimensions
        if time_dimension:
            td: Dict[str, Any] = {"dimension": time_dimension}
            if date_range:
                td["dateRange"] = date_range
            if granularity:
                td["granularity"] = granularity
            query["timeDimensions"] = [td]
        if filters:
            query["filters"] = filters
        if order:
            query["order"] = order
        query["limit"] = min(limit or self.DEFAULT_LIMIT, self.MAX_LIMIT)

        status, error, row_count = "ok", None, 0
        started = time.monotonic()
        try:
            results = await cube_load(query)
            row_count = len(results)
        except Exception as exc:
            logger.error(
                "xuchang_cube_metrics_failed",
                cube=cube,
                query=json.dumps(query, ensure_ascii=False),
                error=str(exc),
            )
            return {
                "success": False,
                "data": None,
                "metadata": {"tool_name": self.tool_name, "cube": cube},
                "summary": f"语义层查询失败: {exc}",
            }

        elapsed = round(time.monotonic() - started, 2)
        sample_data = results
        if context and len(results) > 24:
            saved_path = context.save_data(
                data=results,
                schema="metrics_query_result",
                metadata={"cube": cube, "query": query, "row_count": row_count},
            )
            sample_data = results[:12] + results[-12:]
            logger.info(
                "xuchang_cube_metrics_large_result_saved",
                path=str(saved_path),
                row_count=row_count,
            )

        semantic = cube_metadata(cube, CATALOG)
        data_as_of = self._infer_data_as_of(results)
        if not row_count:
            quality_status = "blocked"
        elif data_as_of:
            quality_status = "ok"
        else:
            quality_status = "degraded"
        payload = {
            "success": True,
            "data": sample_data,
            "metadata": {
                "tool_name": self.tool_name,
                "cube": cube,
                "row_count": row_count,
                "elapsed_seconds": elapsed,
                "truncated_to_sample": len(sample_data) < row_count,
            },
            "count": row_count,
            "sample_count": len(sample_data),
            "data_as_of": data_as_of,
            "quality_status": quality_status,
            "semantic_context": {
                "registry_version": semantic.get("registry_version", 0),
                "dataset": semantic.get("dataset"),
                "grain": semantic.get("grain"),
                "applicability": semantic.get("applicability"),
                "source_window": semantic.get("source_window"),
                "limitations": semantic.get("limitations", []),
                "metric_definitions": {
                    member.split(".", 1)[-1]: semantic.get("measures", {}).get(member.split(".", 1)[-1], {})
                    for member in measures or []
                },
                "quality_guidance": quality_guidance(quality_status),
            },
            "summary": f"查询 {cube} 返回 {row_count} 行({elapsed}s，数据截至 {data_as_of or '未能从结果推断'})",
        }
        contract_errors = validate_result("metric_query", payload)
        if contract_errors:
            logger.warning("xuchang_metric_result_contract_violation", errors=contract_errors)
        return payload

    _TIME_KEY_NAMES = frozenset({
        "datatime", "datadate", "computedat", "period", "datamonth",
        "periodend", "month", "day", "hour",
    })
    _DATE_LIKE = re.compile(r"^\d{4}-\d{2}(-\d{2})?")

    @classmethod
    def _infer_data_as_of(cls, results: List[Dict[str, Any]]) -> Optional[str]:
        values = []
        for row in results:
            for key, value in row.items():
                short_key = str(key).lower().rsplit(".", 1)[-1]
                if short_key not in cls._TIME_KEY_NAMES or value is None:
                    continue
                text = str(value).strip()
                if cls._DATE_LIKE.match(text):
                    values.append(text)
        return max(values) if values else None
