{{ config(
    indexes=[
        {'columns': ['station_code']},
        {'columns': ['uniquecode']},
        {'columns': ['city_code']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '站点目录一致性维度表(5分钟随ODS同步重建)。station_code 为主键口径,uniquecode 为质控等系统的关联键;city_name 已做 bsd_city 去重(该表 code 多层级重复)。新宽表的城市/站点维度一律经本表获取,不再各自 join bsd_city。'",
    ],
) }}

-- dim_station: 站点目录一致性维度表（来自 jiangsu_ods.bsd_station，5分钟增量同步）。
-- 目的：统一站点/城市维度——此前各宽表各自 join bsd_station+bsd_city，
-- 而 bsd_city.code 存在多层级重复（同一地市码2-3行），join 不去重会把行数翻倍。
-- 所有新宽表的城市/站点维度一律经本表获取；bsd_city 的 DISTINCT ON 去重只在此处做一次。
-- dbt table 物化为原子换名重建, 无 DROP/CREATE 空窗(替代原 _new 换名脚本)。
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
