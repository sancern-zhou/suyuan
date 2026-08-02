# Secure Session Resource Download Design

## Context

Unified session resources expose signed, gateway-relative `download_url` values. The
current download menu renders those values as native anchor targets. When the Suyuan
HTTP application is embedded by an HTTPS parent, Chromium classifies the resulting
navigation download as insecure and may block it. The affected PPTX payload itself is
valid; a current resource URL returns the expected presentation MIME type and archive.

A retry can publish a new resource group and supersede the earlier resource IDs. The
client must therefore download from the current catalog object and surface an HTTP
failure instead of silently navigating to an obsolete URL.

## Chosen Design

Centralize ordinary resource downloads in `resourceDownloads.js`:

1. Fetch the current resource's signed `download_url` with `authFetch`.
2. Reject non-2xx responses with a useful error.
3. Convert the response to a Blob and create a short-lived Object URL.
4. Trigger a browser download using the existing normalized filename.
5. Remove the temporary anchor and revoke the Object URL deterministically.

`ResourcePreviewActions` will replace direct download navigation for the primary and
PDF rendition actions with buttons that call this helper. While a download is active,
the action is disabled and displays a downloading label. Failures remain in the action
menu so a blocked, expired, or superseded resource is visible to the user.

Other resource download entry points that still render raw `download_url` anchors will
use the same helper where they are part of the unified product UI. No legacy office,
visualization, or file endpoints will be restored.

## Catalog Consistency

The store must never claim it observed an expected resource version when the catalog
response reports an older version. `resourceVersion` records only the server response;
`requestedVersion` records an in-flight expectation. A refresh that receives an older
catalog remains eligible for a subsequent event or bounded retry. This prevents an
early catalog response from permanently retaining superseded download links.

## Error Handling

- Missing `download_url`: report that the resource is not downloadable.
- Non-success response: include the HTTP status or backend response text.
- Fetch/Blob failure: show the normalized failure message and restore the action.
- Object URLs are revoked in a `finally`-safe cleanup path.
- Catalog refresh failure keeps the last rendered catalog but does not advance its
  observed version.

## Tests

- The shared helper uses authenticated fetch, creates a Blob URL, applies the expected
  filename, clicks once, removes its anchor, and revokes the URL.
- HTTP failures do not create or click a download anchor.
- Resource actions do not contain direct `href="download_url"` navigation.
- A catalog response older than the requested version does not inflate the observed
  version and remains refreshable.
- Existing session-resource lifecycle and preview tests continue to pass.
- The standalone production build contains the unified resource API and excludes all
  legacy `/office-documents` and `/visualizations` API strings.

## Deployment

Build only from `/home/xckj/suyuan/frontend` with `npm run build:standalone`, verify the
required resource-interface strings in `frontend/dist/assets`, then reload
`suyuan-nginx`. TLS termination for the public application remains the infrastructure
level defense-in-depth follow-up; this change removes the browser navigation-download
failure without inventing an HTTPS endpoint that is not currently configured.
