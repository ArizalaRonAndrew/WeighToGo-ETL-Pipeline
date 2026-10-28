# Stage 2: Transformation

## 1. Stage 1 input and batch processing

Stage 2 consumes the in-memory dictionaries handed over by Stage 1; it does not reconnect to or redefine the source database. Required handover values are:

- `parent_extraction_run_id`: the successful Stage 1 extraction run ID.
- `batch_start` and `batch_end`: the extraction window as ISO dates, with `batch_end` exclusive. For October 2026 use `2026-10-01` and `2026-11-01`.
- Assessment, child, and supplement records produced by that same extraction run/window.

The Stage 1 extractor currently returns rows but does not yet generate/persist an extraction run ID. Until that is implemented, the caller must supply the actual run ID used by the extraction handover. Never mix rows from different extraction runs or windows.

The planned schedule is monthly at 02:00 Asia/Manila on the 5th, after Stage 1 completes. Failed or manually held batches are rerun from the same immutable Stage 1 batch, with the same parent run ID and window. `batch_id` is a deterministic UUID derived from that pair; each attempt gets a separate `run_id`. This makes target replacement idempotent: in one database transaction delete prior transformed, profile, and quarantine rows for that `batch_id`, then insert the complete replacement. Preserve prior run metadata by `run_id`. Do not replace target rows unless the replacement transaction can commit completely.

`transform_batch` profiles, transforms, validates, and returns data in memory. `save_transformation_result` can persist that result as separate CSV files under `data/transformed/<YYYY-MM>/<run_id>/`, including the dimension, fact tables, trend aggregates, quarantine, profiles, validations, and run summary. This is a local temporary-file handoff; transformation still uses memory while running, and CSV export is not a transactional database load. The `data/` directory is git-ignored because these files can contain sensitive health data. PostgreSQL load and scheduler connections are not configured in this repository; [transformation_schema.sql](../../pipelines/transformation/transformation_schema.sql) defines the destination contract but must be applied and the transactional loader implemented before claiming database persistence.

## 2. Scope and approved clinical-data interpretation

Inputs are `tbl_children`, `tbl_assessments`, and `tbl_supplements`. Child data is transformed first, then assessment and supplement facts are joined to the active child dimension. The Stage 1 month window is validated again in Stage 2.

The source already supplies `wfa_status`, `hfa_status`, and `wfl_h_status`. By user decision, these existing classifications are passed through as standardized uppercase labels; this stage does **not** calculate WHO z-scores or independently assign nutritional status. True z-score recalculation requires separately approved WHO reference tables, algorithm/version, sex/age rules, and validation; those are not in the repository.

Only rows whose source `status` equals `active` after trimming/case normalization are transformed. The source schema uses `active`/`reject`, not `DELETED`/`CANCELLED`; all non-active rows are quarantined. No other source business status is inferred.

## 3. Profiling

The implementation profiles the current input batch before treatment. It emits one profile row for each nonzero issue with table, column, issue type, up to three sample values, affected record count, input count, computed affected percentage, planned treatment, and rule ID. Sample values are limited to the profiled column; full rejected source rows go only to the restricted quarantine target.

The percentages and examples below are the preliminary values supplied in the lab exercise, **not measurements from a fresh production-wide profile**. The transformer's runtime profile is authoritative for each batch.

| Table | Column | Issue type | Example values | Preliminary affected share | Planned treatment / rule |
|---|---|---|---|---:|---|
| `tbl_children` | `barangay` | Whitespace/casing inconsistency | `" Barangay 1 "`, `"brgy 1"` | 4% (lab estimate) | Trim, collapse spaces, uppercase (C-01/S-04); `brgy` aliases need a separately approved mapping and are not guessed. |
| `tbl_children` | `gender` | Non-standard aliases | `"boy"`, `"M"`, `"girl"` | 2% (lab estimate) | Map recognized aliases to `MALE`/`FEMALE`; otherwise set `UNKNOWN` and retain a warning/profile (S-02). |
| `tbl_assessments` | `weight`, `height` | Non-positive, nonnumeric, or out-of-range values | `-12.5`, `-95.0` | 0.5% (lab estimate) | Quarantine (C-02/S-03). |
| `tbl_supplements` | `date_administered` | Future or invalid date | `2027-11-01` | 1% (lab estimate) | Quarantine future values; invalid conversions are quarantined (C-03/S-01). |
| All source tables | Required columns/values | Missing schema, null identifiers, dates, or measurements | `NULL`, missing column | Measured per batch | Fail affected record closed to quarantine; missing contract columns are critical schema errors (C-05/S-05). |
| All source tables | `id` | Duplicate primary key | Repeated UUID | Measured per batch | Keep newest unique `created_at`; quarantine older rows; quarantine all ties/undated duplicate groups (C-04). |
| Assessment/supplement facts | `child_id` | Orphan/inactive parent reference | UUID absent from active child dimension | Measured per batch | Quarantine fact (B-01). |

Percentages are `affected_records / input_records * 100`, rounded to two decimal places. They must be regenerated for each run; the lab estimates must not be presented as actual source measurements.

## 4. Cleaning rules

Every rule below is linked to a profiling issue or a defined source/business integrity condition.

| Rule ID | Target | Condition | Action | Justification / profiled issue |
|---|---|---|---|---|
| C-01 | `tbl_children.barangay` | Leading/trailing whitespace | Trim; collapse repeated internal whitespace. | Avoid duplicate geographic groups caused by formatting; profile whitespace issue. |
| C-02 | `tbl_assessments.weight`, `height` | Value is zero, negative, non-finite, or otherwise physically invalid | Quarantine row with reason and rule ID. | Invalid anthropometry must not enter counts or downstream indicators; profile measurement issue. |
| C-03 | `tbl_supplements.date_administered` | Date is after processing as-of date | Quarantine row. | Future administrations cannot be included in historical compliance; profile date issue. |
| C-04 | `id` in any source table | Duplicate IDs | Keep only the row with the newest valid `created_at` when there is one unique latest row; quarantine every older row. Quarantine the entire duplicate group if `created_at` is missing/invalid or latest timestamps tie. | Preserve one deterministic source version without arbitrary tie-breaking; profile duplicate issue. |
| C-05 | Required source identifiers/fields | Required column absent or required value null | Quarantine affected row with missing-field reason. | Prevent incomplete records from producing facts or dimensions; profile null/schema issue. |
| C-06 | `tbl_children.dob` | Date is in the future | Quarantine child. | A future birth date is invalid and prevents reliable age calculation. |

Whitespace treatment does not invent a barangay alias map: `"BRGY 1"` remains different from `"BARANGAY 1"` until an authoritative mapping is approved. Blank `barangay`/`purok` values become `UNSPECIFIED` under S-04 rather than disappearing from output.

## 5. Standardization rules

| Rule ID | Target | Input and output standard | Conversion failure |
|---|---|---|---|
| S-01 | `dob`, `date_measured`, `date_administered` | Parse date/date-like input and emit ISO `YYYY-MM-DD` / PostgreSQL `DATE`. | Quarantine row; do not guess an ambiguous date. |
| S-02 | `gender` | Trim/case-fold aliases: `M`/`MALE`/`BOY` → `MALE`; `F`/`FEMALE`/`GIRL` → `FEMALE`. Other values → `UNKNOWN` with a profile/warning. | Preserve record with `UNKNOWN`; issue appears in profile. |
| S-03 | `weight`, `height`, `age_in_months`, `dose_order` | Convert finite measurements to `DECIMAL(5,2)` with half-up rounding (`weight_kg`, `height_cm`); convert age and dose order to integers. | Nonnumeric, non-finite, out-of-range measurements, missing/invalid age integers, or invalid dose integers are quarantined. Non-positive weight/height use C-02. |
| S-04 | `barangay`, `purok` | Trim, collapse whitespace, uppercase; blank/null → `UNSPECIFIED`. | Non-text values are stringified and normalized; source alias is not inferred. |
| S-05 | Required fields/schema | Validate contracted field presence and expected types before use. | Missing fields/columns are quarantined; missing source schema fields are critical and hold the batch. |
| S-06 | Nutritional status/supplement categories | Status labels become trimmed uppercase text; null/blank classifications become `UNCLASSIFIED`. Supplement category must be `Vitamin A` or `Deworming`. | Non-text nutritional statuses and unsupported supplement categories are quarantined. |
| B-05 | `age_months` | Derive full calendar months from child DOB through measurement/administration date; the measurement day must have reached the corresponding birth day. | Date before DOB is quarantined. A valid existing source age mismatch is a warning; the derived value is used. Missing/invalid source age is quarantined under S-03. |

Dates have no time component in these source columns. Timestamps, if encountered, are reduced to their calendar date as represented in the input; no timezone conversion is inferred for a PostgreSQL `DATE`.

## 6. Business transformation rules

| Rule ID | Input / logic | Output | Business reason |
|---|---|---|---|
| B-01 | Inner join assessment/supplement `child_id` to the in-batch active `dim_child.child_key`. | `child_key` foreign key in each fact. Unmatched facts quarantined. | Attribute child health and supplement facts to valid geography/demographics. |
| B-02 | Require business date in `[batch_start, batch_end_exclusive)`. | `assessment_month` / `supplement_month` as `YYYY-MM`. | Keep output aligned to its parent extraction batch and trend period. |
| B-03 | Keep source rows only where normalized `status = ACTIVE`. | Active-only dimension/facts; others quarantined. | Exclude source-rejected rows without assuming unsupported `CANCELLED`/`DELETED` codes. |
| B-04 | Unpivot each assessment into WFA/HFA/WFL classifications, then count by normalized barangay, assessment month, indicator, and status. | `fact_health_trends.total_count`. Each assessment contributes exactly one count to each of three indicators. | Feed the requested Health Trends chart without recalculating supplied classifications. |
| B-05 | Calculate completed age in months from DOB and event date; compare with source age. | `age_months`; disagreement produces a warning. | Provide a consistent age value for downstream validation while retaining source classification decisions. |

No BMI, WHO z-score, or other clinical value is derived here. Supplement facts are transformed but not included in the assessment-only Health Trends aggregation.

## 7. Transformed contract and source-to-target mapping

Targets are in schema `etl`, defined in [transformation_schema.sql](../../pipelines/transformation/transformation_schema.sql). Names use `dim_` for dimensions and `fact_` for facts. Records are batch-scoped for reproducible reruns. `child_key` is the source UUID renamed as the deterministic batch-scoped dimensional key; it is **not** a newly generated surrogate. This avoids unstable surrogate-key assignment before a database loader exists. Child names and parent-contact fields are excluded because they are unnecessary for this chart and increase exposure of identifiable child data.

| Source | Target | Type and transformation |
|---|---|---|
| `tbl_children.id` | `dim_child.child_key`, `source_child_id` | `uuid`; same source key, batch-scoped primary key. |
| `tbl_children.dob` | `dim_child.date_of_birth` | `date`; S-01. |
| `tbl_children.barangay` | `dim_child.barangay_name` | `text`; C-01/S-04, blank → `UNSPECIFIED`. |
| `tbl_children.purok` | `dim_child.purok_name` | `text`; S-04. |
| `tbl_children.gender` | `dim_child.gender` | `MALE`/`FEMALE`/`UNKNOWN`; S-02. |
| `tbl_children.is_ip` | `dim_child.is_ip` | `boolean`; source pass-through. |
| `tbl_children.status` | `dim_child.source_status` | Only `ACTIVE` rows emitted; B-03. |
| `tbl_assessments.id` | `fact_assessment.assessment_id` | `uuid`; source fact key. |
| `tbl_assessments.child_id` | `fact_assessment.child_key` | `uuid`; join to `dim_child`, B-01. |
| `tbl_assessments.date_measured` | `fact_assessment.date_measured`, `assessment_month` | `date`, `CHAR(7)`; S-01/B-02. |
| `tbl_assessments.age_in_months`, `tbl_children.dob` | `fact_assessment.age_months` | `integer`; DOB-derived B-05; mismatch warning. |
| `tbl_assessments.weight`, `height` | `fact_assessment.weight_kg`, `height_cm` | `DECIMAL(5,2)`; S-03/C-02. |
| `tbl_assessments.wfa_status`, `hfa_status`, `wfl_h_status` | same named fact columns | `text`; uppercase/pass-through classifications or `UNCLASSIFIED`; no WHO recalculation. |
| `tbl_supplements.id`, `child_id` | `fact_supplement.supplement_id`, `child_key` | `uuid`; fact key and B-01 join. |
| Supplement date/type/dose/age columns | `fact_supplement.date_administered`, `supplement_month`, `supplement_type`, `dose_order`, `age_months` | `date`, `CHAR(7)`, category/text, integer, integer; S-01/S-03/B-02/B-05. |
| `dim_child.barangay_name` plus assessment month and three status columns | `fact_health_trends.barangay_name`, `assessment_month`, `indicator`, `nutritional_status`, `total_count` | Aggregate key plus positive `BIGINT` count; B-04. |

Primary keys are `(batch_id, child_key)` for `dim_child`, `(batch_id, assessment_id)` for `fact_assessment`, `(batch_id, supplement_id)` for `fact_supplement`, and `(batch_id, barangay_name, assessment_month, indicator, nutritional_status)` for `fact_health_trends`.

## 8. Validation, quarantine, and acceptance

| Validation | Severity | Pass criterion / action on failure |
|---|---|---|
| Record reconciliation, per input table | CRITICAL | `records_read = records_output + records_rejected`. Any mismatch rejects the batch. |
| Output key uniqueness | CRITICAL | Duplicate target keys = 0. |
| Referential integrity | CRITICAL | Every emitted assessment/supplement `child_key` resolves to the same-batch dimension. |
| Business rules | CRITICAL | Emitted facts are active, within the half-open batch window, have positive measurements/valid nonnegative age, and use valid supplement categories; dimension barangay is non-null. |
| Health-trend reconciliation | CRITICAL | Sum of trend counts = 3 × accepted assessment-fact rows. |
| Source versus DOB-derived age | WARNING | Differences are recorded per source row; derived age is used. Warning causes manual review. |
| Profiling findings | INFO/WARNING | Every nonzero issue is reported with affected count/percentage, sample values, and treatment. |

Every rejected source record increments its table's `records_rejected` metric and produces a quarantine item with `batch_id`, `run_id`, `parent_extraction_run_id`, source table/record ID, rule ID, reason, rejected timestamp, and source record. Credential and parent-contact fields are redacted. Quarantine payloads can still contain child/health data and therefore require restricted database permissions and retention controls. `transform_batch` logs each rejection without logging the rejected record itself.

Acceptance threshold is based on the total input rows across all three source tables:

- **APPROVED:** all critical checks pass, and rejection rate is strictly below 1%.
- **MANUAL_REVIEW:** any warning exists or rejection rate is at least 1%; hold the load and request MNAO/operator review.
- **REJECTED:** any critical check fails; do not load target facts; alert the pipeline maintainer/database owner.

The rate is `sum(records_rejected) / sum(records_read)`; an empty input has a zero rate but still requires the operator to confirm that the batch is expected before approval. Rejection records remain quarantined for review regardless of the run decision.

Run metadata includes `run_id`, `parent_extraction_run_id`, deterministic `batch_id`, batch window, start/end timestamps, status, per-table records read/output/rejected, applied rule counts, profile rows, and validation results. Audit and quarantine retention is 12 months; deletion is a monthly scheduled, database-owner-managed job. Restrict write access to the pipeline service account, read access to authorized maintainers/MNAO reviewers, and administration to DBAs. The SQL schema does not create roles or a retention job because target role names and deployment privileges are not configured.

## 9. Use

```python
from pipelines.extractions.extractor import WeighToGoExtractor
from pipelines.transformation.health_trends import transform_batch

period = "2026-10"
extractor = WeighToGoExtractor()
if not extractor.connect():
    raise RuntimeError("Could not connect to Supabase")

assessments = extractor.extract_batch("assessment", period)
children = extractor.extract_batch("children", period)
supplements = extractor.extract_batch("supplements", period)

# Replace with the actual successful Stage 1 run ID when the handover
# metadata is available.
result = transform_batch(
    assessments,
    children,
    supplements,
    parent_extraction_run_id="EXT_20261005_0200",
    batch_start="2026-10-01",
    batch_end="2026-11-01",
)

from pathlib import Path

from pipelines.transformation.health_trends import save_transformation_result

output_dir = (
    Path("data")
    / "transformed"
    / result.batch_start[:7]
    / result.run_id
)
csv_files = save_transformation_result(result, output_dir)
print(f"Transformation CSV files saved under {output_dir}")

if result.status != "APPROVED":
    raise RuntimeError(
        f"Transformation requires action: {result.status}; "
        f"quarantined={len(result.quarantine_records)}"
    )
chart_rows = result.fact_health_trends
```

Run the focused tests from the project root:

```powershell
python -m unittest pipelines.transformation.test_health_trends
```

The chart-only helper `transform_health_trends(assessments, children)` remains available for compatibility. Production batch processing should use `transform_batch`, which supplies profiling, standardization, facts, validation, run context, and quarantine records.
