# Session Upload Attachment Manifest Design

## Summary

User-uploaded attachments must enter the canonical `session_resource_manifests` store before the first model request. Runtime prompts and later requests must use the manifest reference instead of treating a URL embedded in the conversation transcript as an executable resource locator.

This change is deliberately strict:

- there is no runtime fallback from an upload URL to `UploadedFile`;
- historical sessions and transcripts are not backfilled;
- attachments created before deployment must be uploaded again if they are absent from the manifest.

## Problem

The upload API returns an attachment containing `file_id` and a display URL. On the first request, `ReActAgent` queries `UploadedFile` and replaces that URL with the local file path for runtime use. The Web route independently persists the original request attachment in the transcript, so the stored user message contains the URL instead of the normalized path.

On a later request without a repeated attachment payload, the model restores the transcript and sees only the URL. It can therefore call `analyze_image` with the URL even though the uploaded file still exists locally. This violates the manifest's role as the canonical session resource inventory.

The existing manifest collector does not solve this by itself because it captures successful tool outputs, not resources supplied as user input.

## Goals

- Register every valid uploaded attachment in the session manifest before the first model request.
- Use one normalized attachment representation for current-turn runtime input and manifest persistence.
- Prevent transcript text from becoming a competing executable locator source.
- Make a later request able to discover the uploaded image from the manifest without resending the attachment payload.
- Prefer `analyze_image` as the projected resolver for image files when that tool is available.
- Preserve existing behavior for non-image uploaded files and external resources produced by tools.
- Fail explicitly when attachment normalization or manifest persistence cannot guarantee cross-request durability.

## Non-goals

- Runtime URL-to-local-path fallback in `analyze_image` or any other tool.
- Historical transcript scanning or manifest backfill.
- Automatic repair of attachments uploaded before this change.
- Changing uploaded-file retention, deletion, or authorization policy.
- Moving file bytes into the manifest.
- Adding columns to `session_resource_manifests`.

## Chosen Approach

Introduce one shared upload-attachment normalizer at the Agent boundary. It resolves each attachment's `file_id` through `UploadedFile`, validates that a local file record exists, and returns:

1. normalized runtime attachment data containing the local path and MIME type;
2. a `SessionResourceRef` with `kind=file`, `role=attachment`, and a local-path locator.

The reference uses `logical_key=upload:<file_id>` and stores bounded upload metadata including `file_id` and MIME type. The manifest remains the canonical session resource inventory; `UploadedFile` remains the storage record used to resolve the attachment at ingestion.

The normalized attachment references are atomically merged into the manifest before the manifest is loaded and projected for the current model request. This guarantees that the first request and all later requests observe the same resource identity.

## Data Flow

```text
Agent request attachments
        |
        v
UploadAttachmentNormalizer --lookup--> UploadedFile
        |
        +--> normalized runtime attachment (local_path, mime_type)
        |
        +--> SessionResourceRef(role=attachment, kind=file)
                         |
                         v
             session_resource_manifests
                         |
                         v
             ResourceContextProjector
                         |
                         v
       current and subsequent model requests
```

The display transcript stores only the user text plus a non-executable attachment marker containing the attachment name and stable manifest logical key/reference identity. It must not store the upload URL or local path.

## Component Responsibilities

### UploadAttachmentNormalizer

The normalizer:

- accepts the request attachment dictionaries;
- requires a non-empty `file_id` for uploaded attachments;
- loads the matching `UploadedFile` record;
- verifies the record contains a non-empty local path;
- normalizes the attachment type, filename, MIME type, and local path;
- creates an attachment resource reference with `tool_name=user_upload`;
- returns rejected attachment diagnostics without inferring paths from arbitrary URL text.

The normalizer does not download URLs and does not parse historical transcript text.

### ReActAgent

`ReActAgent` calls the shared normalizer after it has a concrete session ID and before constructing the runtime loop. It merges incoming attachment references into the manifest before loading the manifest for context projection.

The current request uses the same normalized attachments returned by the normalizer. The existing inline database lookup and independently constructed attachment path text are removed so attachment normalization has one owner.

If attachment references cannot be persisted, the run returns an explicit fatal resource-durability failure before invoking the model. Continuing with a local attachment that is absent from the canonical manifest would recreate split state.

### Transcript Persistence

The route's transcript helper emits display-only text such as:

```text
[用户上传附件：现场照片.png；资源引用：upload:<file_id>]
```

It never emits `url`, `local_path`, `file_path`, or `path`. The transcript is useful for display and conversational context but is not a resolver input.

### ResourceContextProjector

For a file reference whose metadata MIME type starts with `image/`, the projector selects `analyze_image` when available. Otherwise it selects `read_file`. Non-image file behavior remains unchanged.

The projected line includes the canonical local path already stored in the manifest, allowing the model to call the selected tool directly.

## Identity and Persistence

The reference locator is the normalized absolute local path, preserving compatibility with the existing `ResourceLocator` model and avoiding a schema or JSON contract migration. `logical_key=upload:<file_id>` provides the stable upload slot and deduplicates repeated submission of the same upload in a session.

Reference metadata is bounded to identifiers required for display and resolver selection:

```json
{
  "file_id": "upload UUID",
  "mime_type": "image/png",
  "attachment_type": "image"
}
```

The original public URL is not stored in the manifest reference because it is neither required for local tool execution nor authoritative.

## Error Handling

- Missing or malformed `file_id`: reject the attachment and fail the request before model execution.
- Missing `UploadedFile` row: fail the request as an invalid attachment.
- Missing local path in the row: fail the request as an invalid attachment.
- Manifest load or merge failure: report a resource-persistence failure and do not invoke the model.
- Missing file discovered by a reading tool: preserve existing tool-level missing-file behavior; lifecycle status updates are outside this focused change.

There is no fallback to the URL, because fallback would create a second resource resolution channel and weaken the unique-source guarantee.

## Historical Behavior

Only attachments submitted after deployment are registered. Existing transcript URLs are not scanned, translated, or imported. A user must upload an old attachment again when its session manifest does not contain the resource.

## Security

- The normalizer trusts only the `UploadedFile` lookup result for a local path.
- Arbitrary client-supplied local paths are ignored for uploaded attachments.
- Existing conversation ownership checks remain required before accessing the session manifest.
- Existing tool filesystem restrictions remain required when reading the projected path.
- Public upload URLs are display/API transport values, not authorization or local-resolution inputs.

## Test Strategy

### Unit Tests

- resolve a valid image `file_id` into one normalized runtime attachment and one attachment resource ref;
- reject missing and unknown `file_id` values;
- ensure the resource ref excludes the public URL;
- ensure transcript attachment markers contain no URL or local path;
- project image files through `analyze_image` when available and `read_file` otherwise;
- preserve `read_file` projection for non-image files.

### Integration Tests

- first request registers the uploaded image before model context projection;
- manifest merge failure prevents model invocation;
- second request without attachments projects the same local image path from the manifest;
- restored transcript containing only the display marker cannot supply an executable URL;
- repeated submission of the same `file_id` does not create duplicate active resources.

### Regression Test

Reproduce the reported flow:

1. upload an image whose API response contains a public `/api/upload/<file_id>` URL;
2. run an Agent request with that attachment;
3. run a second request saying “重新读取图片” without attachments;
4. assert the selected image tool receives the local upload path and never receives the public URL.

## Rollout

1. Deploy the attachment normalizer and manifest integration together.
2. Restart all Web and Worker processes.
3. Verify `session_resource_manifest_schema_ensured` appears during startup.
4. Execute the two-request regression test against a newly uploaded image.
5. Treat old sessions without attachment refs as unsupported and require re-upload.
