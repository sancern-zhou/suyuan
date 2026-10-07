{% snapshot bsd_devicetype %}
-- 每日 check 快照(SCD2): 业务列哈希判变, 上游增删改自动留痕。
-- business_columns 宏排除同步元数据列(_sync_batch 每次全量都变, 不排除会全表误判为变更)。
-- 源: jiangsu_ods.bsd_devicetype — 设备类型字典(Code→Name, 27行; dim_device.device_type_name 的来源)
select {{ business_columns(source('jiangsu_ods', 'bsd_devicetype')) }}
from {{ source('jiangsu_ods', 'bsd_devicetype') }}
{% endsnapshot %}
