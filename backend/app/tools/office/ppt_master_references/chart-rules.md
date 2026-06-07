# PPT Master Chart Rules

## Data And Chart Assets

- Data slides must prefer real chart images or PowerPoint native charts.
- Use mock charts only when both real visual assets and structured chart data
  are unavailable.
- Generated chart PNG files must be passed into `create_pptx_with_ppt_master`
  at creation time through the matching outline item.

## Supported Asset Fields

Pass chart or visual image paths through one of these fields:

- `outline[].chart.image_path`
- `outline[].chart.path`
- `outline[].visual.image_path`

The PPT Master generation stage must place the image directly into the chart
area.

## Prohibited

- Do not first generate a mock PPT and then use `edit_pptx` or `replace_slot`
  to guess and replace chart slots.
- Do not hide missing data behind decorative mock charts when real data is
  available upstream.
- Do not turn chart-heavy analysis into many identical chart pages.
