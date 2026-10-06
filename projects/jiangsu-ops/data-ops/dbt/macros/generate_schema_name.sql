{#
  覆盖默认行为: custom schema 按字面使用, 不与 target.schema 拼接。
  这样 snapshots 的 +target_schema: jiangsu_snapshot 就是最终 schema 名,
  models 不指定 schema 时落在 target.schema = jiangsu_mart。
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
