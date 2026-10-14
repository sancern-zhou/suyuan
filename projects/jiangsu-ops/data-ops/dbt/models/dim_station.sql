{{ config(
    indexes=[
        {'columns': ['station_code']},
        {'columns': ['uniquecode']},
        {'columns': ['city_code']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '站点目录一致性维度表(5分钟随ODS同步重建)。station_code 为主键口径,uniquecode 为质控等系统的关联键;city_name 已做 bsd_city 去重(该表 code 多层级重复)。station_type_name 映射自源库 StationType 字典:1国控站/2省控站/3市控站/4区域站/5乡镇站/6省建站/7省乡镇站/9Voc站,其余未知。is_active_provincial=省控站统一口径位(启用省控站101个),省控域分析宽表一律经本位过滤。新宽表的城市/站点/类型维度一律经本表获取,不再各自 join bsd_city。'",
    ],
) }}

-- dim_station: 站点目录一致性维度表（来自 jiangsu_ods.bsd_station，5分钟增量同步）。
-- 目的：统一站点/城市维度——此前各宽表各自 join bsd_station+bsd_city，
-- 而 bsd_city.code 存在多层级重复（同一地市码2-3行），join 不去重会把行数翻倍。
-- 所有新宽表的城市/站点维度一律经本表获取；bsd_city 的 DISTINCT ON 去重只在此处做一次。
-- dbt table 物化为原子换名重建, 无 DROP/CREATE 空窗(替代原 _new 换名脚本)。
-- station_type_name 映射来源: 源库 air_province_bsd.sys_datadictionary(dictionarycode='StationType',
-- 2026-10-14 勘察): 1国控站/2省控站/3市控站/4区域站/5乡镇站/6省建站/7省乡镇站/9Voc站;
-- 8(模范站点)/99(其他)在源字典已停用, 与空类型一并归"未知"。
select
    s.id,
    s.stationcode                       as station_code,
    s.positionname                      as station_name,
    s.uniquecode,
    s.areacode                          as city_code,
    c.name                              as city_name,
    s.towncode,
    s.longitude,
    s.latitude,
    s.address,
    s.stationtypeid                     as station_type_id,
    case s.stationtypeid
        when 1 then '国控站'
        when 2 then '省控站'
        when 3 then '市控站'
        when 4 then '区域站'
        when 5 then '乡镇站'
        when 6 then '省建站'
        when 7 then '省乡镇站'
        when 9 then 'Voc站'
        else '未知'
    end                                 as station_type_name,
    -- 省控站统一口径位(2026-10-14 治理): "省控站"=名录中启用的省控站, 当前101个。
    -- 省控域分析宽表(告警/质控安排/质控补测/质控执行等)一律经本位过滤;
    -- 年内停用的3008A/3022A/3094A/5030A与超站7099A、40开头试点站均为 false。
    (s.stationtypeid = 2 and s.status)  as is_active_provincial,
    s.status,
    s.ismonitor                         as is_monitor,
    s.iscontrast                        as is_contrast,
    s.manager,
    s.builddate,
    s.stoptime,
    s.updatetime,
    now()::timestamp                    as synced_at
from {{ source('jiangsu_ods', 'bsd_station') }} s
left join (
    select distinct on (code) code, name
    from {{ source('jiangsu_ods', 'bsd_city') }}
    order by code, id
) c
    on c.code = case when length(s.areacode) >= 4
                     then rpad(left(s.areacode, 4), 6, '0')
                     else s.areacode end
