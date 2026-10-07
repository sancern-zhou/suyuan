{% snapshot qa_standardmaterialstorage %}
-- 每日 check 快照(SCD2): 业务列哈希判变, 上游增删改自动留痕。
-- business_columns 宏排除同步元数据列(_sync_batch 每次全量都变, 不排除会全表误判为变更)。
-- 源: jiangsu_ods.qa_standardmaterialstorage
select {{ business_columns(source('jiangsu_ods', 'qa_standardmaterialstorage')) }}
from {{ source('jiangsu_ods', 'qa_standardmaterialstorage') }}
{% endsnapshot %}
