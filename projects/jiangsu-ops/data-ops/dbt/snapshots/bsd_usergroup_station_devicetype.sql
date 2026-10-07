{% snapshot bsd_usergroup_station_devicetype %}
-- 每日 check 快照(SCD2): 业务列哈希判变, 上游增删改自动留痕。
-- business_columns 宏排除同步元数据列(_sync_batch 每次全量都变, 不排除会全表误判为变更)。
-- 源: jiangsu_ods.bsd_usergroup_station_devicetype
select {{ business_columns(source('jiangsu_ods', 'bsd_usergroup_station_devicetype')) }}
from {{ source('jiangsu_ods', 'bsd_usergroup_station_devicetype') }}
{% endsnapshot %}
