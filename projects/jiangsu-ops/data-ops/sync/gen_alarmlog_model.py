# -*- coding: utf-8 -*-
"""生成 dbt 模型 mart_station_alarm_log.sql(union 101 告警分片表)。"""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sync-config", type=Path, default=None,
                    help="sync_config.json 路径; 缺省依次找 脚本同目录 → 运行时 E:\\Tools\\suyuan-jiangsu\\sync")
parser.add_argument("--output", type=Path,
                    default=Path(__file__).resolve().parents[4] / "projects/jiangsu-ops/data-ops/dbt/models/mart_station_alarm_log.sql")
args = parser.parse_args()


def _resolve_sync_config(explicit):
    """凭据文件不进 git: 仓库内没有, 运行时副本在脚本同目录。仓库里跑回退运行时绝对路径。"""
    if explicit is not None:
        return explicit.resolve()
    candidates = [
        Path(__file__).resolve().parent / "sync_config.json",
        Path(r"E:\Tools\suyuan-jiangsu\sync\sync_config.json"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "sync_config.json 未找到(找过: %s); 请显式传 --sync-config"
        % "; ".join(str(c) for c in candidates)
    )


SYNC_CONFIG = _resolve_sync_config(args.sync_config)
OUT = args.output.resolve()

cfg = json.loads(SYNC_CONFIG.read_text(encoding="utf-8"))
prefix = "alarmlog_2026_"
stations = sorted(t[len(prefix):] for t in cfg["tables"] if t.startswith(prefix))
if not stations:
    raise SystemExit("no alarmlog shard entries in sync_config.json")

list_sql = ", ".join("'%s'" % s for s in stations)
loop_sql = "\n".join(
    "    select id, uid, type, subcatalog, criticallevel, source, descriptionde,\n"
    "           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,\n"
    "           showmethodint, flagint, healthcount, stationcode\n"
    "    from {{ source('jiangsu_ods', '%s%s') }}%s" % (prefix, s, "" if i == len(stations) - 1 else "\n    union all")
    for i, s in enumerate(stations)
)

MODEL = """{{ config(
    materialized='table',
    tags=['daily'],
    indexes=[
        {'columns': ['station_code', 'alarm_time']},
        {'columns': ['alarm_grade']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '站房/仪器告警长表(每日02:30增量)。一行=一条告警;窗口自2026-07-01;覆盖101省控站(按年分片union);alarm_grade_cn 为级别中文(1/40/60=一般,2/80=严重,3=紧急,20=提示,其余未知)。'",
    ],
) }}

-- mart_station_alarm_log: 站房/仪器告警(长表)
-- 源: air_province_data.dbo.alarmlog_2026_<站>(按年分片; 每年1月换年份后重跑 gen_alarmlog_model.py)
-- 用途: 告警历史分析/取证; 工具 jiangsu_fetch_station_alarm_logs 已改读本 ODS 分片(近24h), 本表提供全窗口语义查询
{{% set alarm_stations = [{LIST}] %}}

with unioned as (
{LOOP}
)
select
    u.id,
    u.stationcode                                as station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    u.uid,
    u.type                                       as alarm_type,
    u.subcatalog,
    u.criticallevel                              as alarm_grade,
    case u.criticallevel
        when 1 then '一般告警'
        when 40 then '一般告警'
        when 60 then '一般告警'
        when 2 then '严重告警'
        when 80 then '严重告警'
        when 3 then '紧急告警'
        when 20 then '提示'
        else '未知'
    end
                                                 as alarm_grade_cn,
    u.source,
    u.descriptionde                              as description,
    u.warningstatus                              as alarm_status,
    u.processstatus                              as process_status,
    u.lauchtime                                  as alarm_time,
    u.lastdetecttime                             as last_detect_time,
    u.resumetime                                 as resume_time,
    u.showmethodint                              as show_method_int,
    u.flagint                                    as flag_int,
    u.healthcount                                as health_count,
    now()::timestamp                             as synced_at
from unioned u
left join {{ ref('dim_station') }} ds
       on ds.station_code = u.stationcode
""".replace("{N}", str(len(stations))).replace("{LIST}", list_sql).replace("{LOOP}", loop_sql)
MODEL = MODEL.replace("{{% set", "{% set").replace("%}}", "%}")

OUT.write_text(MODEL, encoding="utf-8", newline="\n")
print("wrote %s (%d stations)" % (OUT, len(stations)))
