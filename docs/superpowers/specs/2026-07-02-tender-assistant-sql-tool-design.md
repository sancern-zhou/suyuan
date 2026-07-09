# Tender Assistant SQL Tool Design

## Goal

Assistant mode should be able to answer questions about stored tender crawling data in SQL Server.
The tool must reuse the existing SQL query implementation while exposing only tender-related tables.

## Scope

Add one assistant-visible SQL query tool:

- Tool name: `execute_tender_sql_query`
- Default database: `XcAiDb`
- Allowed tables:
  - `tender_notices`
  - `tender_candidates`
  - `tender_fetch_runs`

The tool supports the same two operations as the existing SQL tools:

- `describe_table`: inspect one allowed table's schema and sample row.
- `sql`: execute a read-only SQL Server `SELECT` or `WITH` query.

## Security Boundary

The tool uses the existing `BaseSQLQueryTool` and `SQLValidator` behavior:

- Only `SELECT` or `WITH` queries are allowed.
- Mutating or administrative SQL keywords are blocked.
- Referenced tables must be in the tender table whitelist.
- Multi-statement SQL is blocked.
- Query row count is capped by the existing SQL tool limit.
- Result externalization uses the existing execution context behavior.

The general `execute_sql_query` tool is not added to assistant mode. This avoids exposing monitoring or other database tables through the assistant surface.

## Assistant Integration

Register `execute_tender_sql_query` in the global tool registry and add it to `ASSISTANT_TOOL_NAMES`.
The native function schema will describe tender table fields and common query patterns, so the assistant can choose the tool directly for tender storage questions.

## Testing

Automated tests cover:

- Tool schema and defaults.
- Assistant mode exposes `execute_tender_sql_query`.
- The tool allows tender table SQL.
- The tool rejects non-tender tables and non-read-only SQL.

Manual or smoke verification covers:

- `describe_table='tender_notices'` against the real SQL Server.
- A recent tender count query against the real SQL Server.
