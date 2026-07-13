# O3 Upper Standard Identity Audit Design

## Goal

Extend the operations work-order audit for `RF_HY_O3VALUEPASS` so that O3
transfer result values and upper-standard identity fields are checked against
the attached transfer workbook, while missing source evidence and conflicting
history are reported for manual review instead of being converted into false
deterministic failures.

## Confirmed Field Mapping

The current RF template stores the upper-standard data in these fields:

| Business value | RF field |
| --- | --- |
| Upper-standard model | `DELIVER6VALUE` |
| Upper-standard device number | `DELIVERFROM6VALUE` |
| Upper-standard serial number | `AVALUE` |
| Upper-standard transfer date | `WORKDENSITY6VALUE` |
| Upper-standard transfer formula | `DELIVERTO6VALUE` |
| Upper-standard expiry date | `BVALUE` |

`DEVICEDELIVERMODEL` and `DELIVERFC` are the slope and intercept of the current
work-standard transfer. They must not be compared with the slope and intercept
embedded in the upper-standard formula.

## Evidence Findings

Real 2026 records use multiple valid upper standards. Examples include
`T700 / 4696`, `T703 / 569`, and several `49ips` instruments. Consequently, a
global rule such as "the device number must be N.A." is invalid.

The same `49ips` certificate batch is also represented by different workbook
conventions, including `49ips / N.A. / CM...`, `TE / 49ips / CM...`, and
`49ips / TE-49IPS / CM...`. Some RF rows disagree with their own workbook, and
some workbooks carry the questionable convention into the RF row. Therefore:

1. RF-to-workbook comparisons are deterministic.
2. Workbook-to-certificate interpretation is review evidence unless a
   business-maintained canonical batch record exists.
3. Historical majority is not authoritative because repeated copied errors are
   common.

## Rule Design

### 1. RF-to-XLS value comparison

Extend `ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH` to dynamically locate the
upper-standard section on the first workbook sheet. Accept both section labels
`上级臭氧传递标准` and `参考光电仪`, then read the value paired with each label:

- `型号`
- `设备号`
- `序列号`
- `传递日期` or `认证日期`
- `传递公式` or `认证公式`
- `传递有效期限` or `认证有效期限`

Compare these values with the six RF fields. Normalize whitespace, ASCII case,
full-width punctuation, date separators, formula spacing, and common empty
markers. Do not merge model, device number, and serial number into one value.

The existing slope, intercept, change-rate, and current transfer-formula checks
remain in the same rule. Numeric values use the precision displayed in the RF
form.

### 2. Missing workbook review item

Add `ATTACHMENT_O3_VALUE_PASS_XLS_MISSING_REVIEW` when an O3 value-pass form has
no XLS/XLSX attachment. This is a standalone manual-review category, not a
claim that the slope or identity values are wrong. Evidence includes the work
order code and the six RF identity fields.

### 3. Historical batch conflict review

Within the current audit dataset, construct an O3 upper-standard fingerprint
from normalized serial number, transfer formula, transfer date, and expiry
date. When two or more forms share a sufficiently complete fingerprint but
their model/device-number pair differs, add
`RF_O3_UPPER_STANDARD_HISTORY_CONFLICT_REVIEW` to each conflicting order.

This rule reports the observed alternatives and supporting order codes. It is
a manual-review item because history can contain repeated copied errors. It
must not select the majority value as correct.

### 4. Certificate evidence

Certificate filenames and paths are included in mismatch and history-conflict
evidence when available. Existing visual/OCR infrastructure may later extract
certificate fields, but this implementation does not promote model mapping
from a scanned certificate to a deterministic failure. The source certificate
often exposes only instrument name and instrument number, while the RF form
separates model, device number, and serial number.

## Processing Flow

1. Read the O3 RF form and select the preferred XLS/XLSX attachment.
2. Parse the workbook first sheet by labels rather than fixed row numbers.
3. Compare slope/result fields and upper-standard identity fields.
4. Emit one deterministic mismatch issue containing all failed comparisons.
5. If no workbook exists, emit the missing-workbook review issue.
6. After per-order checks, group O3 forms by complete upper-standard
   fingerprint and emit history-conflict review issues.

## Error Handling

- An unreadable XLS remains an attachment read error under the existing
  mismatch rule.
- Missing labels do not invent values. They are included as parse evidence but
  only become a deterministic mismatch when the workbook clearly contains the
  section and a required labeled value is present.
- PDF-only evidence does not trigger numeric slope comparison.
- Date parsing accepts Excel serial dates and common Chinese or separator-based
  date formats.
- Formula comparison ignores presentation differences but preserves numeric
  coefficients and signs.

## Testing

Focused tests cover:

- all six identity fields matching;
- model, device number, and serial number mismatches;
- date and formula normalization;
- `参考光电仪` and `上级臭氧传递标准` layout variants;
- `T700/4696` and `T703/569` values without global `49ips` assumptions;
- missing XLS producing only a review issue;
- complete batch fingerprints producing conflict review items;
- incomplete fingerprints producing no history conflict;
- existing slope/intercept/change tests remaining green.

## Non-Goals

- No global allowlist that forces every upper standard to `49ips`.
- No automatic correction of RF or XLS values.
- No majority-vote selection of a canonical historical value.
- No deterministic certificate-field verdict based only on multimodal output.
