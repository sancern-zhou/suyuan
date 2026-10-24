{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['working_order_code']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- wo_commonfile_links 工单附件索引（一行 = 一条附件记录）。
-- 源: guangdong_ods.wo_commonfile_links（id 高水位追加）。附件本体在源系统。
-- 契约: sync/datasets/wo_commonfile_links.yaml。
select
    id, working_order_code, function_code, type_code,
    file_name, file_path, create_user_id, create_time,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'wo_commonfile_links') }}
