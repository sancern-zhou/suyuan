# PPT Master QA Rules

## Validation

- `success=true` only means the PPTX file was generated. It does not mean the
  deck is ready for delivery.
- After generation, always inspect `qa_status`, `quality_gate`, and
  `revision_tasks`.
- QA output describes facts only: issue type, severity, slide, location,
  evidence metrics, and preview artifacts. QA must not decide how to rewrite
  the deck.
- If validation is enabled, inspect `validation` and the rendered preview
  artifacts.

## Quality Gate

- If `validate_pptx.success=false`, `quality_gate.status` must be
  `rewrite_required`.
- Key QA issues must be copied into `quality_gate.issues`.
- `qa_status=passed` means the deck can be delivered.
- `qa_status=needs_revision` means use `revision_tasks` as structured issue
  inputs, inspect the previous `slide_plan`, and let the Agent decide the local
  `plan_patch`.
- `qa_status=qa_failed` means fix validation, rendering, or font problems
  before judging quality.

## Fonts

- Use fonts available in the current rendering environment.
- Prefer `Microsoft YaHei`.
- On Linux, fallback fonts may include Noto, WenQuanYi, or SimHei.
