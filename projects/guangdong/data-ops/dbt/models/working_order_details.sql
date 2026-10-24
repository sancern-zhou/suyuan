{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['working_order_code']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- working_order_details 工单流程明细（一行 = 工单一个流程步骤）。
-- 源: guangdong_ods.working_order_details（id 增量 + 每日全量 upsert）。
-- 契约: sync/datasets/working_order_details.yaml；processtaskid 映射为 process_task_id。
select
    id, working_order_code, process_step,
    processtaskid            as process_task_id,
    process_user_id, process_start_time, process_end_time,
    process_status, process_time, expense, submit_remark,
    description_ta, participate_user_ids, dispatch_status,
    standby_device_code, image_path, alarm_reason,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'working_order_details') }}
