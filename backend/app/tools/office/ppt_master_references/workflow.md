# PPT Master Workflow

Use this workflow for formal or business PPT generation. It replaces the old
deck/PptxGenJS main path.

## Applicable Scenarios

- Government or state-owned enterprise briefing.
- Business summary.
- Project proposal or implementation plan.
- Data analysis consultation.
- Roadshow, sales, teaching, or research presentation.

## Process

1. Clarify the goal: purpose, audience, setting, page range, delivery format,
   and whether content confirmation is required.
2. Research and gather materials: read attachments, query required data, and
   collect source facts before designing slides.
3. Draft the content in QMD or an equivalent structured outline. This content
   draft carries arguments, sections, chart captions, and conclusions; it is
   not the slide layout plan.
4. Create chart/image assets as PNG files where needed, preferably before PPT
   generation, so the slide plan can reference real assets.
5. Refine and confirm the content draft: reduce redundancy, decide the core
   message for each future slide, and ask the user to confirm when the task is
   a formal report or executive deck. If the user explicitly asks for direct
   generation or the content is already complete, this confirmation can be
   skipped.
6. Plan the deck: read `slide-plan-rules.md` and convert confirmed content
   into `slide_plan[].shapes` page by page. The Agent decides coordinates, text
   density, image fit, and visual hierarchy; the tool draws those primitives.
7. If the detailed `slide_plan` would exceed 8 body pages, contains many
   shapes, or includes many chart/table pages, do not send the whole plan in
   one tool call. First generate a small skeleton deck with
   `create_pptx_with_ppt_master`, then add or replace pages in batches of 3-5
   pages with `create_pptx_with_ppt_master(operation="append"/"replace"/"patch")`.
   For short appended batches, `batch_slides` plus `after_slide` is acceptable.
   For long batches or pages with many shapes, write the JSON payload to a file and pass
   `slide_plan_path` or `plan_patch_path` instead of inlining it.
8. Generate the PPTX with `create_pptx_with_ppt_master` for short decks, or
   use the skeleton-plus-batches flow for long decks. The output project must
   include the current `slide_plan.v*.json`.
9. Run QA: inspect `qa_status`, `quality_gate`, structured issues, page PNGs,
   and montage. Use montage for global visual review and page PNGs for
   slide-level facts.
10. Run visual review on the montage when available. Visual review can identify
   global composition problems, but page-level fixes should use the structured
   QA issues and the corresponding page PNG.
11. Revise with `plan_patch`: the Agent reads the previous `slide_plan`, writes
    only local changes, and calls `create_pptx_with_ppt_master(operation="patch")` so the
    same renderer redraws the deck.
12. Repeat QA and visual review until the deck is deliverable, or clearly
    report the remaining issues.

## Required Tool

Formal business PPT uses `create_pptx_with_ppt_master` with business goal and
structured outline input. The tool does not accept `suyuan.deck.v2` as its
main input.

For high-quality formal decks, prefer `slide_plan` over fixed template slots.
`outline` is acceptable for simple drafts, but chart-heavy, image-heavy, or
executive-facing decks should provide explicit shapes so the Agent can use
python-pptx primitives directly.

For long decks, explicit shapes must be batched. Each revision batch must use
the latest `data.next_revision_base_plan_path` or `data.slide_plan_path`
returned by the previous generation step. Do not keep applying patches to the
original skeleton plan after later batches have created newer plan versions.
If a batch payload is large, the Agent should write it as JSON first and pass
`plan_patch_path`; short append-only batches may still use `batch_slides` and
`after_slide`.

QMD or an equivalent structured document is the content draft. `slide_plan` is
the visual execution plan. QA output is factual evaluation data, not an editing
plan. The Agent decides the `plan_patch`.

## Prohibited

- Do not use old `suyuan.deck.v2` as the formal business PPT main input.
- Do not use lower-level `create_pptx` or PptxGenJS renderer for formal
  business PPT.
- Do not bypass the tool by manually importing PPT tool classes through
  `execute_python`.
- Do not put background, solution, budget, plan, and conclusion all on one
  slide.
