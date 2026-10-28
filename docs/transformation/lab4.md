# Stage 2: Data Transformation Documentation

## 1. Transformation Input and Processing Specification

**Input Source**
* **Staging Area:** Extracted raw health data records staged in memory as dictionaries via Python or in Supabase/PostgreSQL staging tables.
* **Run Context:** Records extracted for a specific parent extraction run (e.g., `EXT_20261005_0200`) representing the previous calendar month's batch window.

**Batch Processing Method**
* **Tool:** PostgreSQL SQL serves as the primary transformation engine, orchestrated by a Python Scheduler.
* **Schedule:** Monthly batch execution at 02:00 Asia/Manila on the 5th of each month.
* **Window:** All records measured or administered within the previous calendar month.
* **Reruns:** Reruns are idempotent; they use a delete-and-insert mechanism driven by the primary keys (`id`) and batch period to prevent duplicates. 

**Transformation Scope**
* **Tables Processed:** `tbl_children`, `tbl_assessments`, and `tbl_supplements`.
* **Transformations Applied:** Calculation of age in months, application of WHO z-score logic to determine nutritional statuses, validation of anthropometric measurements, and aggregation of total counts grouped by month and barangay.

**Dependencies and Assumptions**
* **Processing Order:** The `tbl_children` dimension is validated and transformed before processing the `tbl_assessments` and `tbl_supplements` fact records.
* **Assumptions:** Barangay Nutrition Scholars (BNS) must submit data before the extraction cutoff.

## 2. Data Profiling and Issue Identification

| Table | Column | Issue Type | Example | Affected Records | Planned Treatment |
|---|---|---|---|---|---|
| `tbl_children` | `barangay` | Inconsistent casing and trailing spaces | " Barangay 1 ", "brgy 1" | 4% | Trim spaces and convert to title case (Rule C-01) |
| `tbl_children` | `gender` | Non-standard categories | "boy", "M", "girl" | 2% | Standardize to "MALE" or "FEMALE" (Rule S-02) |
| `tbl_assessments` | `weight`, `height` | Negative values | -12.5, -95.0 | 0.5% | Reject to quarantine and log (Rule C-02) |
| `tbl_supplements` | `date_administered` | Out of bounds/Future date | 2027-11-01 | 1% | Reject to quarantine (Rule C-03) |

## 3. Data Cleaning Rules

| Rule ID | Target | Condition | Action | Justification |
|---|---|---|---|---|
| C-01 | `tbl_children.barangay` | Leading/trailing spaces | Trim whitespace | Ensures consistent grouping for barangay-level analytics. |
| C-02 | `tbl_assessments.weight`, `height` | Value less than 0 | Reject to quarantine table | Negative anthropometric values are physically impossible and invalidate calculations. |
| C-03 | `tbl_supplements.date_administered` | Date is in the future | Reject to quarantine table | Prevents logical errors in compliance reporting and age calculation. |
| C-04 | All extracted tables | Duplicate `id` | Keep latest record by `created_at` | Maintains primary key integrity during idempotent batch reruns. |

## 4. Standardization and Data Type Rules

| Rule ID | Column | Source Format | Standard Format | On Failure |
|---|---|---|---|---|
| S-01 | `date_measured`, `date_administered`, `dob` | Mixed date strings or timestamps | ISO 8601 `YYYY-MM-DD` (DATE) | Reject to quarantine and log. |
| S-02 | `gender` | Mixed text ("M", "boy", "Male") | "MALE" or "FEMALE" | Set to "UNKNOWN" and log. |
| S-03 | `weight`, `height` | Raw numeric | `DECIMAL(5,2)` | Reject to quarantine and log. |
| S-04 | `barangay`, `purok` | Mixed casing | Uppercase string | Set to "UNSPECIFIED". |

## 5. Business Transformation Rules

| Rule ID | Input Columns | Logic | Output Column | Business Reason |
|---|---|---|---|---|
| B-01 | `child_id` (assessments), `id` (children) | Inner join `tbl_assessments` to `tbl_children` | N/A (relational match) | Connects the anthropometric facts to child demographics for geographic grouping. |
| B-02 | `date_measured` | Extract year and month | `assessment_month` | Groups totals by month for nutritional status trend tracking. |
| B-03 | `status` | Exclude records where `status = 'DELETED'` or `status = 'CANCELLED'` | (Filter) | Soft-deleted records should not inflate nutritional or distribution counts. |
| B-04 | `wfa_status`, `barangay`, `assessment_month` | Group by barangay and month, counting each `wfa_status` category | `total_count` | Pre-aggregates totals to serve reporting dashboards and malnutrition analysis. |

## 6. Transformed Data Contract and Naming Convention

| Source Column | Target Column | Source Type | Target Type | Transformation Applied |
|---|---|---|---|---|
| `tbl_children.id` | `child_key` | `uuid` | `uuid` | Renamed to denote dimensional surrogate/primary key. |
| `tbl_children.barangay` | `barangay_name` | `text` | `VARCHAR` | Trimmed and uppercased (C-01, S-04). |
| `tbl_assessments.weight` | `weight_kg` | `numeric(5,2)` | `DECIMAL(5,2)` | Validated > 0 (C-02). |
| `tbl_assessments.wfa_status` | `wfa_status` | `text` | `VARCHAR` | 1:1 mapping, validated against WHO standard categories. |
| (Derived from join) | `total_count` | N/A | `INTEGER` | Aggregated count of nutritional statuses per barangay and month (B-04). |

## 7. Transformation Validation and Data Quality Checks

| Check Name | Target | Purpose | Validation Criteria | Severity |
|---|---|---|---|---|
| Record reconciliation | All output tables | Detect lost or silently dropped records | `input_count = output_count + rejected_count` | Critical |
| Key uniqueness | `child_key`, `assessment_id` | Prevent duplicate facts or dimensions | Duplicate count = 0 | Critical |
| Referential integrity | `fact_assessment.child_key` | Prevent orphan assessment records | 100% match in `dim_child` | Critical |
| Null check | `barangay_name` | Ensure geographic aggregation is possible | Null rate is 0% | Critical |

## 8. Transformation Metadata and Log Specification

| Field | Purpose | Example |
|---|---|---|
| `run_id` | Unique ID of the pipeline transformation run | `TRN_20261005_0230` |
| `parent_run_id` | Extraction run this batch came from | `EXT_20261005_0200` |
| `batch_window` | Data range processed | `2026-09-01 to 2026-09-30` |
| `table_name` | Target table transformed | `fact_assessments` |
| `records_read` | Rows received from extraction | `5,240` |
| `records_output` | Rows successfully produced/transformed | `5,215` |
| `records_rejected` | Rows quarantined due to cleaning rules | `25` |
| `rules_applied` | Records modified per cleaning rule (does not affect reconciliation) | `C-01: 50; S-02: 12` |
| `status` | Result of the run | `SUCCESS` |

## 9. Log Retention, Rejected Data, and Access

* **Storage Location:** Metadata logs and quarantine tables (storing rejected records, rejection reason, rule ID, and batch ID) are stored in the dedicated `etl` schema within the PostgreSQL ETL audit database.
* **Retention Period:** 12 months for transformation logs and rejected records, matching the extraction retention policy to provide rolling audit context.
* **Access Permissions:** The pipeline service account has `INSERT` and `SELECT` rights. Authorized pipeline maintainers and MNAO reviewers have read-only access. Full administrative access is restricted to database administrators.
* **Deletion:** A scheduled PostgreSQL retention job permanently deletes run records and quarantine entries older than 12 months.

## 10. Transformation Acceptance and Handover Rules

| Overall Condition | Acceptance Decision | Pipeline Action |
|---|---|---|
| All critical tables PASS and rejection rate is < 1% | APPROVED | Mark `SUCCESS` and proceed to the Load stage. |
| One or more non-critical WARNING or rejection rate > 1% | MANUAL REVIEW | Hold batch handover. Alert MNAO to verify if missing data or excessive rejects require source correction. |
| One or more critical FAIL (e.g., referential integrity broken) | REJECTED | Stop pipeline. Quarantine records, alert maintainer, and retry after fixing. |

## 11. Common Transformation Problems and Mitigation

| Problem | Possible Cause | Impact | Mitigation |
|---|---|---|---|
| Duplicate records after a rerun | Pipeline restarts a failed batch without idempotent logic | Inflated anthropometric counts and skewed nutritional statistics | Use delete-and-insert or upserts via PostgreSQL by batch ID and primary keys. |
| Late-arriving records | BNS enters prior month's assessments after the 5th of the month | Missing data in barangay operational reports | Process a wider lookback window or execute an approved manual rerun of the month once data is verified. |
| Row multiplication after a join | Child dimension duplicates due to source data entry errors | Inflated assessment counts surpassing the input | Enforce `child_key` uniqueness validation prior to join; deduplicate based on `created_at` (Rule C-04). |
| Unexpected schema change | Supabase source column renamed or type changed | Transformation SQL scripts fail | Extraction schema preflight prevents this; if passed, type conversion logic rejects and logs unmatched formats. |
