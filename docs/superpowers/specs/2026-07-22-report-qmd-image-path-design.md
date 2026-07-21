# Report QMD Image Path Reliability Design

## Goal

Ensure Yuncheng tracing reports always render local images from a normalized report package, and return actionable failures when an image reference cannot be resolved.

## Scope

This change covers three requested areas:

1. Clarify the Yuncheng tracing skill's source-QMD image-path contract.
2. Prevent the renderer from replacing the normalized package QMD with an external source QMD.
3. Add hard image-reference and Quarto resource-warning validation with actionable error messages.

The collector's flat evidence-directory layout remains unchanged. Existing report packages without an external `source_qmd` continue to render as before.

## Path Contract

There are two distinct documents:

- **Source QMD:** Stored in `evidence_dir`. Because collected images are stored in the same directory, Markdown image references use bare relative filenames such as `trajectory.png` and `visibility.png`.
- **Package QMD:** Stored in `reports/{report_id}/report.qmd`. `create_report_package` copies supplied image assets into `assets/charts/` and rewrites references to package-local paths such as `assets/charts/trajectory.png`.

The Agent must not invent `assets/{filename}` paths. It passes the real source image paths through `create_report_package.assets` and lets the package tool determine the destination path.

## Skill Changes

Update the Yuncheng tracing skill to state explicitly:

- Resolve every source-QMD image reference relative to `report.qmd.parent`.
- Use bare filenames for images in `evidence_dir`.
- Do not use `assets/*.png` in the source QMD.
- Do not manually predict package paths.
- Before calling `create_report_package`, verify every selected image exists and pass its real path in `assets`.
- After packaging, run validation and repair the source QMD or asset list when validation returns a missing-resource error.

Include correct and incorrect examples so the instruction is unambiguous.

## Renderer Behavior

The report package QMD is the only render input for HTML and DOCX. The renderer must not copy external `source_qmd` content over `reports/{report_id}/report.qmd`.

`source_qmd` remains metadata that identifies the editable source and supports freshness checks. When the source is newer, the system must report that the package needs rebuilding instead of silently overwriting the normalized package. Package creation remains responsible for translating source content and assets into a renderable package.

Rendering methods therefore:

1. Resolve `reports/{report_id}/report.qmd`.
2. Validate local image references relative to the package directory.
3. Render that package QMD.

They never render the external source path directly and never snapshot it into the package.

## Hard Validation

Before invoking Quarto, inspect local Markdown image references in the package QMD. Ignore remote URL schemes and supported API references handled by existing normalization. For each local reference:

1. Strip query and fragment components.
2. Resolve it relative to the package QMD directory.
3. Reject paths escaping the package directory.
4. Require the target to be an existing regular file.

If validation fails, return or raise an error containing:

- The QMD path.
- Every unresolved image reference.
- The resolved filesystem path attempted.
- A repair hint telling the Agent to pass the real image file through `create_report_package.assets` and reference the resulting `assets/charts/{filename}` package path.

Quarto output must also be checked. A successful process exit accompanied by `Could not fetch resource` is treated as a render failure. The failure message includes the relevant warning lines so the Agent can repair and retry.

`validate_report_package` performs the same local-reference checks and returns structured missing-resource details rather than reporting success based only on output-file existence.

## Error Handling Contract

Expected failure wording is concise and actionable, for example:

```text
Report image validation failed for .../report.qmd:
- reference: assets/visibility.png
  resolved_path: .../reports/example/assets/visibility.png
  reason: file does not exist
Repair: pass the real image path in create_report_package.assets and use the copied package path assets/charts/visibility.png, then validate again.
```

The Agent should receive this failure through the existing tool result/error path and be able to edit the QMD or correct the asset list before retrying.

## Testing

Add regression coverage for:

- The Yuncheng skill's bare-filename source-QMD rule and prohibited `assets/*.png` example.
- Preview rendering preserving an already normalized package QMD even when metadata contains an external source QMD.
- DOCX rendering selecting the package QMD rather than the external source QMD.
- Missing local images failing before Quarto runs, with the reference, resolved path, and repair hint in the message.
- `Could not fetch resource` in Quarto output failing even when Quarto exits successfully.
- Valid `assets/charts/*.png` references continuing to render.
- `validate_report_package` returning failure and structured details for missing image resources.

## Compatibility

The external source path remains recorded for editing, artifact presentation, and staleness detection. The behavioral change is limited to rendering: external source content can no longer bypass package normalization. Existing packages with valid package-local image paths are unaffected.
