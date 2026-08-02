# Unified Resource Download, Product Layout, and Excel Editing

## Goal

Fix the resource preview download path and file-product action layout, and restore interactive Excel editing without restoring the removed Office preview APIs or introducing a second resource lifecycle.

## Decisions

- Collabora/LibreOffice Online is out of scope for this change.
- Unified session resources remain the only catalog, authorization, content, download, and version boundary.
- Existing uploaded and generated resources use the same preview host and actions.
- Historical data migration is not required.

## Download behavior

Ordinary resource downloads are real browser download links backed by each resource's signed `download_url`. They do not enter an asynchronous loading state. QMD render/export actions remain asynchronous because they may create a new rendition before downloading it.

The original filename and format are preserved. A preview rendition such as PDF or HTML must not replace the primary file when the user chooses the original download.

## File-product layout

Each product card has a content area and a fixed right-hand action area. `打开` and `下载` stay together in that action area. Renditions and version information occupy a separate row under the content and cannot change the action buttons' placement.

## Excel interaction

The spreadsheet renderer loads the current resource through its signed content URL and supports:

- switching between workbook sheets;
- selecting and editing cells;
- visible row and column headers;
- reloading the current server version;
- saving edits.

Saving writes the edited workbook through a new resource-scoped action. The backend validates the active session, resource, capability, signed identity, and file type, then publishes the edited workbook as a new version of the same resource group. The catalog version changes, the frontend refreshes the group, and preview/download select the new active version.

The save path must not expose filesystem paths to the browser and must not reintroduce `/api/office/open-excel`, `/api/office/save-excel`, or `/api/office/download-excel`.

## Error handling

- A missing or expired content/download ticket produces an actionable preview or download error.
- Save conflicts or invalid workbook payloads leave the existing active version unchanged.
- Failed catalog refresh leaves the editor content intact and offers reload/retry.
- A save control is disabled while saving, but ordinary downloads never show an indefinite spinner.

## Verification

Automated coverage must demonstrate:

- clicking the preview's original-download control starts a browser download;
- a product with an HTML rendition keeps `打开` and `下载` aligned;
- Excel loads multiple sheets, accepts cell changes, and publishes a new active resource version on save;
- the downloaded Excel is the active original-format workbook;
- the production bundle contains unified resource routes and no removed Office or visualization routes.
