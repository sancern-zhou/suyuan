{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['working_order_code']},
        {'columns': ['station_id']},
        {'columns': ['create_time']},
        {'columns': ['order_type']},
        {'columns': ['order_status']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- working_orders 工单主表（契约层，一行 = 一张运维工单，全类型含作废）。
-- 源: guangdong_ods.working_orders（dbo.working_orders 兼容视图，update_time 水位增量）。
-- 契约: sync/datasets/working_orders.yaml；字段与 ODS 一致，附 refreshed_at。
select
    id, working_order_code, station_id, device_id,
    order_title, order_content, order_type, order_status,
    urgency_type, maintenance_type, create_time, update_time,
    finish_time, plan_finish_time, order_overtime, total_overtime,
    total_expense, workflow_id, current_workflow_point,
    current_process_status, create_user_id, current_user_id,
    department_id, contract_id,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'working_orders') }}
