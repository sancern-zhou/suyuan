# Correlation Heatmap Design

Use `correlation_heatmap` for pollutant correlation matrices, station-metric
correlation checks, or other symmetric coefficient tables that should be
rendered as a report image.

## Data Contract

Preferred data:

```json
{
  "labels": ["SO2", "NO2", "PM10", "PM2.5", "CO", "O3_8H"],
  "matrix": [
    [1.00, 0.30, 0.66],
    [0.30, 1.00, 0.33],
    [0.66, 0.33, 1.00]
  ]
}
```

`matrix` must be a square numeric matrix whose row and column count equals
`labels.length`. Do not pass an ECharts heatmap option.

## Design Rules

- Use a diverging color scale fixed to `[-1, 1]` for correlation coefficients.
- Annotate cells with two decimal places when the matrix is report sized.
- Keep labels short; use pollutant names or abbreviations.
- Do not include figure numbers in the chart title.
- Put data source, sample period, and calculation method in report text.

## Useful Options

- `colorbar_label`
- `cmap`

