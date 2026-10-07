{% snapshot bsd_moniter_parameter %}
-- 每日 check 快照(SCD2): 业务列哈希判变, 上游增删改自动留痕。
-- business_columns 宏排除同步元数据列(_sync_batch 每次全量都变, 不排除会全表误判为变更)。
-- 源: jiangsu_ods.bsd_moniter_parameter — 设备型号健康参数阈值字典(每日全量, 上下限/预警限; 供 dim_device_parameter; 开SCD2快照)
select {{ business_columns(source('jiangsu_ods', 'bsd_moniter_parameter')) }}
from {{ source('jiangsu_ods', 'bsd_moniter_parameter') }}
{% endsnapshot %}
