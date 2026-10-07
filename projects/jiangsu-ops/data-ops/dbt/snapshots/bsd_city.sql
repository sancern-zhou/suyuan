{% snapshot bsd_city %}
-- 每日 check 快照(SCD2): 业务列哈希判变, 上游增删改自动留痕。
-- business_columns 宏排除同步元数据列(_sync_batch 每次全量都变, 不排除会全表误判为变更)。
-- 源: jiangsu_ods.bsd_city — 地市字典(code 多层级重复, join 必须去重)
select {{ business_columns(source('jiangsu_ods', 'bsd_city')) }}
from {{ source('jiangsu_ods', 'bsd_city') }}
{% endsnapshot %}
