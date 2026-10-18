{{ config(
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
{% set alarm_stations = ['3001a', '3002a', '3003a', '3004a', '3005a', '3006a', '3007a', '3009a', '3010a', '3011a', '3012a', '3013a', '3014a', '3015a', '3016a', '3017a', '3018a', '3019a', '3020a', '3021a', '3023a', '3024a', '3025a', '3026a', '3027a', '3028a', '3029a', '3030a', '3031a', '3032a', '3033a', '3034a', '3035a', '3036a', '3037a', '3038a', '3039a', '3040a', '3041a', '3042a', '3043a', '3044a', '3045a', '3046a', '3047a', '3048a', '3049a', '3050a', '3051a', '3052a', '3053a', '3054a', '3055a', '3056a', '3057a', '3058a', '3059a', '3060a', '3061a', '3062a', '3063a', '3064a', '3065a', '3066a', '3067a', '3068a', '3069a', '3070a', '3071a', '3072a', '3073a', '3074a', '3075a', '3076a', '3077a', '3078a', '3079a', '3080a', '3081a', '3082a', '3083a', '3084a', '3085a', '3086a', '3087a', '3088a', '3089a', '3090a', '3091a', '3092a', '3093a', '3095a', '3096a', '3097a', '3098a', '3099a', '3100a', '3101a', '3102a', '3103a', '3104a'] %}

with unioned as (
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3001a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3002a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3003a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3004a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3005a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3006a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3007a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3009a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3010a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3011a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3012a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3013a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3014a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3015a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3016a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3017a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3018a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3019a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3020a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3021a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3023a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3024a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3025a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3026a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3027a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3028a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3029a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3030a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3031a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3032a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3033a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3034a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3035a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3036a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3037a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3038a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3039a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3040a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3041a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3042a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3043a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3044a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3045a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3046a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3047a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3048a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3049a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3050a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3051a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3052a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3053a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3054a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3055a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3056a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3057a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3058a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3059a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3060a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3061a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3062a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3063a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3064a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3065a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3066a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3067a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3068a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3069a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3070a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3071a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3072a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3073a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3074a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3075a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3076a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3077a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3078a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3079a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3080a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3081a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3082a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3083a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3084a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3085a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3086a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3087a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3088a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3089a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3090a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3091a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3092a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3093a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3095a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3096a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3097a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3098a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3099a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3100a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3101a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3102a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3103a') }}
    union all
    select id, uid, type, subcatalog, criticallevel, source, descriptionde,
           warningstatus, processstatus, lauchtime, lastdetecttime, resumetime,
           showmethodint, flagint, healthcount, stationcode
    from {{ source('jiangsu_ods', 'alarmlog_2026_3104a') }}
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
