# Session File Upload Resource Schema Fix

## Problem

The unified session resource contract permits ordinary file resources without a
document or visualization presentation. `ResourceDeclaration`, the ORM model,
and migration `009_create_session_resources.sql` therefore allow
`presentation_type` and `presentation` to be null.

The startup schema definition created these columns, plus `logical_key`, with
`NOT NULL` constraints. The production table has those constraints. A chat
upload creates a normal `file` resource with no presentation, so PostgreSQL
rejects it and the upload endpoint rolls the file back before returning
`503 resource_store_unavailable`.

## Chosen Approach

Align every schema source with the canonical resource contract and repair the
existing production table through an idempotent migration.

- `logical_key`, `presentation_type`, and `presentation` are nullable for
  ordinary resources.
- Presented document and visualization resources retain application-level
  validation requiring a logical key and a matching presentation payload.
- The startup schema definition must match the ORM and migration definitions so
  a new environment cannot recreate the incompatible constraints.
- A new migration drops the three stale `NOT NULL` constraints. Re-running it
  is safe and it does not rewrite or delete resource data.
- Upload registration failures log the original exception before returning the
  stable public error code.

Assigning a fake presentation type to uploaded images is explicitly rejected:
an image attachment is a file resource, not automatically a document or a
visualization.

## Data Flow

1. The upload endpoint writes the file and its `uploaded_files` row.
2. It creates a `ResourceDeclaration(kind=file, role=source)`.
3. The session resource repository stores the resource with nullable
   presentation fields.
4. If resource registration fails, the existing rollback behavior removes the
   uploaded row and file, and the server logs the underlying exception.
5. On success, the file remains available through the existing upload URL and
   appears in the unified session resource list.

## Testing

- Add a schema contract test that fails while the startup DDL marks the three
  optional columns `NOT NULL`.
- Verify the new migration contains idempotent `DROP NOT NULL` operations.
- Keep existing resource model and repository tests green, including presented
  document and visualization resources.
- Apply the migration to the configured PostgreSQL database and inspect
  `information_schema` to confirm the fields are nullable.
- Perform a real authenticated or direct backend upload against a disposable
  session, confirm HTTP 200 and a stored unified resource, then clean up the
  disposable upload/session records and file.

## Deployment

This is a backend and database change only. No frontend build or Nginx reload is
required. The migration is applied before the final upload verification. The
running backend does not need a restart for the database constraint repair, but
the corrected startup DDL takes effect on future process deployments.
