# PPT Master Slide Plan Contract

This document is not a general PPT design guide. It records only the project
contract for using `create_pptx_with_ppt_master.slide_plan` in from-scratch
formal business PPT generation.

## Responsibility Split

- Agent decides page strategy, content tradeoff, coordinates, hierarchy,
  image usage, and revision actions.
- `create_pptx_with_ppt_master` draws the provided primitive shapes with
  python-pptx, registers artifacts, and runs QA.
- Do not use `slide_plan` as a template slot filler. Existing template-based
  generation has been removed from the Agent path because its quality is not
  reliable enough for formal delivery.

## Page Contract

`slide_plan` is an array of body pages. The tool automatically adds the cover
as slide 1, so the first `slide_plan` item becomes slide 2.

Each item may contain:

```json
{
  "title": "页面标题",
  "message": "页面核心结论",
  "role": "content",
  "points": ["可选要点"],
  "shapes": []
}
```

`shapes` is required for precise layout. If `shapes` is omitted, the page is
created but contains only what the deterministic renderer can infer elsewhere.

## Shape Contract

Supported `type` values:

- `text`, `textbox`, `title`, `body`
- `image`, `picture`
- `table`
- `rect`, `rectangle`, `card`

Supported coordinate units:

- default or `unit: "in"`: inches on 16:9 slide size `13.333 x 7.5`.
- `unit: "relative"`: `x/w` are slide-width ratios, `y/h` are slide-height
  ratios.
- `unit: "emu"`: PowerPoint EMU values.

Supported image `fit` values:

- `contain`: preserve full image inside the target box.
- `cover`: preserve aspect ratio, fill the target box, and apply PowerPoint
  crop values so the picture remains within the box.
- `stretch`: force target box dimensions; may distort the image.

Unknown shape types are ignored. Shapes with non-positive width or height are
ignored.

## Current Renderer Limits

- Text supports plain text plus `font_size`, `color`, `bold`, and
  `align: left|center|right`.
- Table primitives support plain editable PowerPoint tables through `rows`,
  basic font size, header fill/text color, body fill, and body text color.
- Rich text runs, lines, arrows, icons, rounded corners, shadows, and vertical
  alignment are not part of the current `slide_plan` renderer.
- Complex charts, maps, highly styled tables, and diagrams should be generated
  upstream as image assets and inserted with `type: "image"`.
- The renderer enables PowerPoint word wrapping, but it does not solve content
  summarization. The Agent must shorten or split content before drawing.

## QA Contract

After generation, inspect these fields before delivery:

- `data.qa_status`
- `data.quality_gate`
- `data.revision_tasks`
- `data.validation.pages[].png_path`
- `data.validation.montage_path`
- `data.validation.issues`

`success=true` only means the file was created. If `qa_status` is
`needs_revision`, revise the previous `slide_plan` with a local `plan_patch`
and rerun `create_pptx_with_ppt_master`; do not present the deck as final. Use
individual page PNGs for page-level fixes and montage only for overall visual
review.

## Minimal Examples

Metric/chart mixed page:

```json
{
  "title": "运营态势总览",
  "message": "核心指标整体改善，但臭氧仍是夏季治理压力点",
  "shapes": [
    {"type": "title", "x": 0.55, "y": 0.35, "w": 7.8, "h": 0.5, "text": "运营态势总览", "font_size": 32, "bold": true},
    {"type": "text", "x": 0.58, "y": 0.95, "w": 8.8, "h": 0.35, "text": "核心指标整体改善，但臭氧仍是夏季治理压力点", "font_size": 15, "color": "64748B"},
    {"type": "card", "x": 0.65, "y": 1.65, "w": 2.7, "h": 1.35, "fill": "F8FAFC", "line": "CBD5E1"},
    {"type": "text", "x": 0.88, "y": 1.88, "w": 2.2, "h": 0.35, "text": "PM2.5", "font_size": 15, "bold": true},
    {"type": "text", "x": 0.88, "y": 2.25, "w": 2.2, "h": 0.5, "text": "-8.6%", "font_size": 30, "bold": true, "color": "0F766E"},
    {"type": "image", "x": 4.1, "y": 1.45, "w": 8.2, "h": 4.9, "path": "/abs/path/chart.png", "fit": "contain"}
  ]
}
```

Editable table page:

```json
{
  "title": "重点城市指标对比",
  "message": "表格用于呈现少量结构化对比数据",
  "shapes": [
    {
      "type": "table",
      "x": 0.75,
      "y": 1.45,
      "w": 11.85,
      "h": 2.4,
      "rows": [
        ["城市", "PM2.5", "同比"],
        ["广州", "28", "-6%"],
        ["深圳", "22", "-8%"]
      ],
      "font_size": 12,
      "header_fill": "174A7C",
      "header_color": "FFFFFF"
    }
  ]
}
```

Relative-coordinate chart insight page:

```json
{
  "title": "污染过程贡献拆解",
  "message": "高值过程主要由区域传输和本地二次生成叠加驱动",
  "shapes": [
    {"type": "title", "unit": "relative", "x": 0.045, "y": 0.045, "w": 0.62, "h": 0.075, "text": "污染过程贡献拆解", "font_size": 31, "bold": true},
    {"type": "image", "unit": "relative", "x": 0.055, "y": 0.22, "w": 0.58, "h": 0.64, "path": "/abs/path/source_chart.png", "fit": "contain"},
    {"type": "card", "unit": "relative", "x": 0.68, "y": 0.24, "w": 0.255, "h": 0.18, "fill": "F8FAFC", "line": "CBD5E1"},
    {"type": "text", "unit": "relative", "x": 0.70, "y": 0.27, "w": 0.215, "h": 0.1, "text": "区域传输贡献在午后快速抬升，是过程峰值的主因。", "font_size": 15}
  ]
}
```
