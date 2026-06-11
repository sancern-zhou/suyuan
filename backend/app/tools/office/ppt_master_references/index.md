# PPT Master Reference Index

Read this file first, then read only the documents needed for the requested
PPT task. The tool schema is compact on purpose; detailed PPT generation
rules live in these progressive reference files.

## Always Read For Business PPT

- `workflow.md`: required before creating formal or business PPT files with
  `create_pptx_with_ppt_master`.
- `slide-plan-rules.md`: required before using `slide_plan` for from-scratch
  formal business PPT generation.
- `output-contract.md`: required when checking the tool result, generated
  project files, QA status, or delivery readiness.

## Read When Needed

- `layout-rules.md`: required for agendas, section pages, page sequencing,
  chart-heavy decks, or any request involving page structure.
- `chart-rules.md`: required when slides contain data charts, generated chart
  PNG files, PowerPoint native charts, or visual assets.
- `qa-rules.md`: required when `run_validation` is enabled, strict quality is
  requested, validation fails, or revision tasks are returned.

## Routing Rules

- Formal or business PPT generation uses `create_pptx_with_ppt_master`.
- From-scratch formal business PPT should prefer Agent-planned
  `slide_plan[].shapes` when page quality matters, especially for chart,
  diagram, metric, roadmap, or mixed-content slides.
- Use `execute_python` only for upstream data preparation, chart/image asset
  generation, or narrow compatibility work that the PPT tools cannot cover.
- Do not use old deck structures, the PptxGenJS renderer, or direct manual
  imports of PPT tool classes as the main creation path.

## Generated Project Files

`create_pptx_with_ppt_master` creates per-run project artifacts. These are
outputs for the current deck, not global design rules:

- `design_spec.md`: generated design spec for the current PPT.
- `spec_lock.json`: generated master/layout lock for the current PPT.
- `page_plan.json`: generated page plan for the current PPT.
- `pages/page-*.svg`: generated SVG drafts for individual pages.
