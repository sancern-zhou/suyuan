# Scatter Chart Design

Use `scatter` for x-y relationships, correlation checks, and distribution of
paired numeric observations.

## Data Contract

```json
{"x": [1.2, 2.4, 3.1], "y": [8.0, 9.5, 11.2]}
```

Both `x` and `y` must be numeric arrays with the same length.

## Design Rules

- Use axis labels that name the variables and units.
- Avoid scatter plots for categorical x values; use bar charts instead.
- If the relationship needs regression, filtering, grouping, or annotation not
  supported by the schema, prepare the data upstream before calling this tool.
- Split dense comparisons into multiple images rather than encoding too many
  groups in one scatter plot.

## Useful Options

- `x_label`
- `y_label`
- `unit`
- `reference_lines`
