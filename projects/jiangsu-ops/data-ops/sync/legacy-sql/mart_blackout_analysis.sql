-- mart_blackout_analysis: 停电单宽表
-- 一行 = 一张停电报备单(mtc_BlackOut, 全量 65 行,每日刷新)。
-- 口径注意: stop_type 0/1 语义待业务确认(按分布猜测 0=计划停电/1=故障停电)。
-- 场景: 高值时段停电合规核验(停电时段 vs 离线/断数告警)。
DROP TABLE IF EXISTS jiangsu_mart.mart_blackout_analysis;
CREATE TABLE jiangsu_mart.mart_blackout_analysis AS
SELECT
    b.id,
    b.stationcode                     AS station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    b.stoptype                        AS stop_type,
    CASE b.stoptype WHEN '0' THEN '计划停电(待确认)' WHEN '1' THEN '故障停电(待确认)' ELSE b.stoptype END AS stop_type_cn,
    b.ordertype_text                  AS order_type_text,
    b.sdttime                         AS start_time,
    b.edttime                         AS end_time,
    EXTRACT(EPOCH FROM (b.edttime - b.sdttime)) / 3600.0 AS duration_hours,
    b.iscancel                        AS is_cancel,
    b.abnormal,
    b.remark,
    b.createtime                      AS source_create_time,
    b.updatetime                      AS source_update_time,
    now()::timestamp                  AS synced_at
FROM jiangsu_ods.mtc_blackout b
LEFT JOIN jiangsu_mart.dim_station ds
       ON ds.station_code = b.stationcode;

COMMENT ON TABLE jiangsu_mart.mart_blackout_analysis IS
'停电单宽表(全量65行,每日刷新)。stop_type 语义待业务确认,列名已带(待确认)标记;duration_hours=结束-开始。用于停电时段与离线/断数告警的合规核验。';

CREATE INDEX IF NOT EXISTS ix_mbol_station ON jiangsu_mart.mart_blackout_analysis (station_code);
CREATE INDEX IF NOT EXISTS ix_mbol_start ON jiangsu_mart.mart_blackout_analysis (start_time);

GRANT SELECT ON jiangsu_mart.mart_blackout_analysis TO agent_reader;
