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

1. Clarify the goal: purpose, audience, setting, page range, and delivery
   format.
2. Structure the content: cover, background, issue, solution, data, case,
   plan, and conclusion as needed.
3. Choose a style: `business_clean`, `government_consulting`, or
   `consulting`.
4. Lock layouts: avoid repeated visual structure on adjacent pages; data pages
   should prefer a large chart plus insight cards.
5. Draw page by page: each page communicates one core message and chooses the
   right form for the content.
6. Check quality: layout diversity, overflow, fonts, image clarity, PDF/PNG
   preview, and validation report.
7. Export: return editable PPTX plus project directory, design spec, layout
   lock, page plan, and SVG drafts.

## Required Tool

Formal business PPT uses `create_pptx_with_ppt_master` with business goal and
structured outline input. The tool does not accept `suyuan.deck.v2` as its
main input.

## Prohibited

- Do not use old `suyuan.deck.v2` as the formal business PPT main input.
- Do not use lower-level `create_pptx` or PptxGenJS renderer for formal
  business PPT.
- Do not bypass the tool by manually importing PPT tool classes through
  `execute_python`.
- Do not put background, solution, budget, plan, and conclusion all on one
  slide.
