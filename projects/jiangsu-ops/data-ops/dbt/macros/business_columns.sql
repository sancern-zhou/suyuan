{#
  列出关系的业务列(排除同步引擎元数据列 _src_incremental/_sync_batch/_synced_at)。
  供 snapshots 使用: _sync_batch 每次全量刷新都变, 若参与 check 哈希会把全表
  误判为"变更", 快照变成噪音。运行时自省列名, 免去手工维护 19 张表的列清单。
  注意:
  - 不能用 `select * exclude (...)` — 那是 Snowflake/DuckDB 方言, PG 报语法错
  - 列自省用 get_columns_in_relation(source() 本身就是 Relation), 解析期
    (ParseDatabaseWrapper)无连接类 API → if execute 守卫, 解析期返回占位 '*'
    (该分支不会真正编译进物化 SQL)
#}
{% macro business_columns(relation) -%}
    {%- if not execute -%}
        *
    {%- else -%}
        {%- set cols = adapter.get_columns_in_relation(relation) -%}
        {%- set keep = [] -%}
        {%- for c in cols -%}
            {%- if c.name not in ('_src_incremental', '_sync_batch', '_synced_at') -%}
                {%- do keep.append(adapter.quote(c.name)) -%}
            {%- endif -%}
        {%- endfor -%}
        {{ keep | join(', ') }}
    {%- endif -%}
{%- endmacro %}
