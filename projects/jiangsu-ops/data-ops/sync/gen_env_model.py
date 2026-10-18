# -*- coding: utf-8 -*-
"""生成 dbt 模型 mart_station_env_power.sql(内嵌分片站点清单)。

读取 integrated_h_<年>_* 条目生成 union 清单(sync_config.json 依次找 脚本同目录 →
运行时 E:\\Tools\\suyuan-jiangsu\\sync, 也可 --sync-config 显式指定);
每年 1 月换年份重跑 gen_env_sync_config.py 后, 重跑本脚本刷新模型。
"""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sync-config", type=Path, default=None,
                    help="sync_config.json 路径; 缺省依次找 脚本同目录 → 运行时 E:\\Tools\\suyuan-jiangsu\\sync")
parser.add_argument("--output", type=Path,
                    default=Path(__file__).resolve().parents[4] / "projects/jiangsu-ops/data-ops/dbt/models/mart_station_env_power.sql")
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
prefix = "integrated_h_"
shard_prefix = "integrated_h_2026_"  # 分片源名(换年份时同步改 gen_env_sync_config.py 的 YEAR)
stations = sorted(
    t[len(prefix):].split("_", 1)[1]  # integrated_h_2026_3001a -> 3001a
    for t in cfg["tables"] if t.startswith(prefix)
)
if not stations:
    raise SystemExit("no env shard entries found in sync_config.json")

list_sql = ", ".join("'%s'" % s for s in stations)
loop_sql = "\n".join(
    "    select id, stationcode, timepoint, pollutantcode, monvalue, mark\n"
    "    from {{ source('jiangsu_ods', '%s%s') }}%s" % (shard_prefix, s, "" if i == len(stations) - 1 else "\n    union all")
    for i, s in enumerate(stations)
)

MODEL = """{{ config(
    materialized='table',
    tags=['daily'],
    indexes=[
        {'columns': ['station_code', 'timepoint']},
        {'columns': ['pollutant_code']},
        {'columns': ['station_code', 'id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '站房动环小时长表(每日02:30增量)。一行=一站x一小时x一动环项;窗口自2026-10-01;覆盖{N}/101省控站(3072A源库无分片表);当日实时仍走API工具;按年分片,每年1月换年份。'",
    ],
) }}

-- mart_station_env_power: 站房动环供电/温湿度小时数据(长表)
-- 源: air_province_data.dbo.integrated_h_2026_<站>(按年分片; 每年1月用 gen_env_sync_config.py 换年份后重跑 gen_env_model.py)
-- 覆盖: {N}/101 省控站(3072A 无 2026 分片表), 窗口自 2026-10-01(用户决策回填窗口)
-- 编码: 小时表实测 11 项(VA/VB/VC/IA/IB/IC/StationTemp/StationHum/PipeTemp/PipeHum/SamplePipeSPress);
--       API 默认 25 项中其余项(钢瓶压力/烟感/水浸等)小时表无数据, 实时取证走 jiangsu_fetch_station_environment_history
{% set env_stations = [{LIST}] %}

with unioned as (
{LOOP}
)
select
    u.id,
    u.stationcode                                as station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    u.timepoint,
    u.pollutantcode                              as pollutant_code,
    case when u.monvalue ~ '^-?[0-9]+(\\.[0-9]+)?$'
         then u.monvalue::double precision end   as monvalue,
    u.monvalue                                   as monvalue_text,
    u.mark,
    now()::timestamp                             as synced_at
from unioned u
left join {{ ref('dim_station') }} ds
       on ds.station_code = u.stationcode
""".replace("{N}", str(len(stations))).replace("{LIST}", list_sql).replace("{LOOP}", loop_sql)

OUT.write_text(MODEL, encoding="utf-8", newline="\n")
print("wrote %s (%d stations)" % (OUT, len(stations)))
