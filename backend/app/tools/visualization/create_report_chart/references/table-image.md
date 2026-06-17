# Table Image Design

Use `table_image` only when a compact table must be embedded as an image in a
report. Prefer report-native markdown or Word tables when the table is long or
needs to be copied.

## Data Contract

```json
{
  "columns": ["Metric", "Value", "Unit"],
  "rows": [
    ["PM2.5", "18", "ug/m3"],
    ["PM10", "45", "ug/m3"]
  ]
}
```

## Design Rules

- Keep tables small enough to read at Word insertion size.
- Use short column names.
- Move detailed notes to report text instead of placing paragraphs inside cells.
- Split wide tables into multiple smaller tables.
- Do not use `table_image` for raw data dumps.
