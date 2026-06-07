# PPT Master Output Contract

`create_pptx_with_ppt_master` returns a generated PPTX and a project directory
with intermediate design artifacts.

## Required Result Fields

Always inspect these fields after generation:

- `data.file_path`
- `data.project_dir`
- `data.design_spec_path`
- `data.spec_lock_path`
- `data.page_plan_path`
- `data.quality_gate`
- `data.qa_status`
- `data.revision_tasks`
- `data.validation`, if validation was enabled

## Generated Project Artifacts

- `design_spec.md`: current deck design spec.
- `spec_lock.json`: current deck master/layout lock.
- `page_plan.json`: current deck page plan.
- `pages/page-*.svg`: current deck page SVG drafts.

These files are generated artifacts for one PPT project. They should be read
when inspecting or revising that specific output, but they are not global tool
rules.

## Delivery Rule

Deliver the PPT only when `qa_status` is `passed`, or clearly state that it is
an initial draft and list the returned revision tasks.
