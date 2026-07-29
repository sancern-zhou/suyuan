# Authenticated Image Blob Loading Design

## Goal

Make every cached image referenced by `/api/image/{image_id}` render reliably in both the right-side visualization panel and Markdown/QMD content. Requests must use the existing authenticated HTTP client so the same implementation works in development mock-auth mode and in company Bearer-token mode.

## Current Failure

`ImagePanel` and `MarkdownRenderer` currently pass `/api/image/...` directly to an HTML `<img>` element. This bypasses the frontend API-base mapping from `/api` to `/api/suyuan`, so the development frontend can return the SPA HTML instead of image bytes. A native `<img>` request also cannot attach the `Authorization` and `SysCode` headers required in company-auth mode.

The image endpoint returns raw image bytes with an `image/*` content type. The old placeholder loader incorrectly attempts to parse that response as JSON.

## Chosen Approach

Add a small shared image-loading module that fetches an API image through `authFetch`, validates the response, converts it to a Blob, and creates a browser Object URL. Both rendering paths will use this module.

Alternatives rejected:

- Rebuilding Markdown image rendering around Vue child components would require a broader replacement of the existing `v-html` renderer.
- A Service Worker interceptor would add global request lifecycle and caching complexity for a local rendering problem.
- Making `/api/image` public would weaken access control for business-generated images.

## Components and Data Flow

### Shared API image loader

A focused frontend utility will:

1. Accept an `/api/image/{image_id}` path.
2. Call `authFetch`, allowing the existing client to map the path to the configured gateway prefix and attach authentication headers.
3. Reject non-success HTTP responses.
4. Reject responses whose `Content-Type` is not `image/*`.
5. Read the response with `response.blob()` and return a newly created Object URL.

The caller owns the returned Object URL and must revoke it when it is replaced or no longer used.

### Visualization `ImagePanel`

For `[IMAGE:id]` and `/api/image/id` inputs, `ImagePanel` will use the shared loader rather than assigning the API path directly to `<img src>`. Data URLs, Blob URLs, and external URLs keep their existing direct rendering behavior.

The component will track whether its current source is an owned Object URL. Before replacing it and during component unmount, it will call `URL.revokeObjectURL`. A monotonically increasing request generation will prevent a slow earlier request from replacing a newer `src`; any stale Object URL will be revoked immediately.

HTTP failures, invalid content types, or fetch failures set the existing error state and emit `ready`, preserving the panel's current user-visible behavior.

### Markdown/QMD images

`MarkdownRenderer` will retain the current Markdown-it and `v-html` architecture. After rendered HTML reaches the DOM, it will find image elements whose original source begins with `/api/image/`. Each image will be fetched with the shared loader and its DOM `src` replaced by the Object URL.

Each render pass gets a generation identifier. Results from an obsolete render pass will not mutate the current DOM and their Object URLs will be revoked. Before a new pass and during unmount, all Object URLs owned by the renderer will be revoked. Data URLs, Blob URLs, and external images are left unchanged.

Failed Markdown image requests retain the original source and receive the existing browser error behavior; the failure is logged with the original API path for diagnosis.

## Compatibility and Security

- Development mock-auth mode works because `authFetch` still performs API-base mapping.
- Company-auth mode works because `authFetch` attaches `Authorization: Bearer ...` and `SysCode` before creating the local Blob URL.
- Image cache routes remain protected; no public-route or backend authentication changes are required.
- Word, QMD, HTML, PDF, and office-file download flows are out of scope because they already use authenticated Blob downloads.
- HTML and PDF iframe authorization behavior is out of scope and should be audited separately before enforcing company authentication in environments that rely on direct iframe URLs.

## Testing

Tests will be written before implementation and will cover:

- The shared loader uses the authenticated request path, accepts image responses, and creates an Object URL.
- HTTP failures and non-image responses are rejected without producing an Object URL.
- `ImagePanel` resolves API sources through the Blob loader and revokes owned URLs on replacement and unmount.
- A stale `ImagePanel` request cannot overwrite a newer source.
- `MarkdownRenderer` replaces all `/api/image/...` DOM sources while leaving data and external images unchanged.
- Markdown rerenders and unmounts revoke owned Object URLs, and stale results cannot modify current content.

Relevant focused frontend tests will run first, followed by the complete frontend test suite and production build.

## Success Criteria

- The supplied `matplotlib_*` image URLs render in the visualization panel and Markdown/QMD content.
- Browser image requests no longer fetch raw `/api/image/...` paths directly.
- All Blob URLs created by these renderers are released deterministically.
- Existing non-API image rendering remains unchanged.
- Focused tests, the full frontend test suite, and the production build pass.
