# WeighToGo ETL: Stage 1 — Data Extraction

## 1. Source system and extraction specification

- **Source system:** WeighToGo child nutrition monitoring application.
- **Purpose:** Record child demographic profiles, anthropometric assessments, and vitamin/deworming distributions for municipal nutrition monitoring.
- **Source database and format:** Supabase-hosted PostgreSQL. The extraction accesses PostgreSQL tables through the Supabase REST API (PostgREST over HTTPS) and receives JSON responses, represented in Python as dictionaries.
- **Local extract format:** The extractor returns dictionaries for in-memory pipeline use. When run directly, it also writes the selected assessment batch as a CSV file under `data/extracted/` (for example, `assessment_2026-10.csv`). The directory is git-ignored because extracts contain sensitive health data. CSV is a local handoff/export format; the API response itself remains JSON.
- **Extraction type:** Monthly-window incremental batch. Each run extracts all rows whose business date falls within the selected calendar month. This is a bounded-period extract, not a row-change/CDC watermark. A rerun re-reads the whole month; downstream loading must therefore use the source primary key and run/period to avoid duplicate target records.
- **Tool:** Python `WeighToGoExtractor`, using HTTPS requests and the configured Supabase project URL and read-only API key. Secrets are supplied through environment variables or the ignored project `.env`; credentials and personal data must not be written to logs.
- **Schedule:** Recommended production schedule is 02:00 Asia/Manila on the 5th of each month, extracting the entire previous calendar month. The 4-day delay is an operational grace period for barangay submissions. The data owner must publish the submission cutoff (end of the previous month) and alert the pipeline operator if the schedule is changed.
- **Window and logic:** For a selected month, use inclusive start and exclusive next-month start: `date_column >= month_start AND date_column < next_month_start`. Use `tbl_assessments.date_measured` for assessments and `tbl_supplements.date_administered` for distributions. The child batch contains distinct children referenced by either monthly dataset. All pages are fetched in stable primary-key order. The exact same predicates are used for source counts and extraction.
- **Operational note:** The current Python module implements the REST query, explicit source-column allowlist, monthly window, pagination, and CSV export for direct runs. Scheduling, source-schema preflight, exact source-count reconciliation, duplicate-key checks, structured run-log persistence, and approval routing are target controls in this specification and must be implemented/configured before claiming full production compliance. Parent extraction run metadata is not yet persisted by the extractor; the Stage 2 caller must supply the actual run ID and window until that handover is implemented.

## 2. In-scope tables, columns, and rationale

Only the following tables and columns are in the extraction contract. User authentication data (`tbl_users`, including email and password) is explicitly out of scope. Parent contact details are excluded because they are not required for the stated ETL purpose.

### `public.tbl_children`

| Column | PostgreSQL type | Key / relationship | Reason for extraction |
|---|---|---|---|
| `id` | `uuid` | Primary key | Stable child identifier and join key. |
| `dob` | `date` | — | Age validation and demographic reporting. |
| `barangay` | `text` | — | Required geographic grouping and completeness checks. |
| `purok` | `text` | — | Required local grouping for authorized operational reporting. |
| `gender` | `text` | — | Demographic grouping and validation. |
| `is_ip` | `boolean` | — | Required demographic grouping where authorized. |
| `status` | `text` | — | Preserve the source record status for audit and downstream rules. |
| `created_at` | `timestamp with time zone` | — | Source lineage and record-age diagnostics. |

`name`, `parent_name`, and `parent_contact` are deliberately not extracted; they are not needed for this pipeline's stated aggregation purpose. Child profiles provide only the demographic and geographic attributes needed for joining and grouping.

### `public.tbl_assessments`

| Column | PostgreSQL type | Key / relationship | Reason for extraction |
|---|---|---|---|
| `id` | `uuid` | Primary key | Stable assessment identifier and duplicate detection. |
| `child_id` | `uuid` | Foreign key to `tbl_children.id` | Link assessment to child profile. |
| `date_measured` | `date` | Monthly extraction window | Select the assessment period and support trends. |
| `weight` | `numeric(5,2)` | — | Raw anthropometric measurement. |
| `height` | `numeric(5,2)` | — | Raw anthropometric measurement. |
| `age_in_months` | `integer` | — | Age at assessment and validation input. |
| `wfa_status` | `text` | — | Preserve source weight-for-age classification. |
| `hfa_status` | `text` | — | Preserve source height-for-age classification. |
| `wfl_h_status` | `text` | — | Preserve source weight-for-length/height classification. |
| `status` | `text` | — | Preserve source record status for audit and downstream rules. |
| `created_at` | `timestamp with time zone` | — | Source lineage and record-age diagnostics. |

### `public.tbl_supplements`

| Column | PostgreSQL type | Key / relationship | Reason for extraction |
|---|---|---|---|
| `id` | `uuid` | Primary key | Stable distribution identifier and duplicate detection. |
| `child_id` | `uuid` | Foreign key to `tbl_children.id` | Link distribution to child profile. |
| `supplement_type` | `text` | — | Distinguish Vitamin A and deworming distributions. |
| `dose_order` | `integer` | — | Preserve distribution sequence. |
| `age_in_months` | `integer` | — | Age at administration and validation input. |
| `date_administered` | `date` | Monthly extraction window | Select the distribution period and support compliance reporting. |
| `status` | `text` | — | Preserve source record status for audit and downstream rules. |
| `created_at` | `timestamp with time zone` | — | Source lineage and record-age diagnostics. |

The child foreign keys in both operational tables reference `public.tbl_children(id)`. Extraction does not update or delete source rows.

## 3. Extraction validation checks

Every check records its result (`PASS` or `FAIL`), observed value, expected criterion, and affected table in the run log. Any failed blocking check prevents handover to the next pipeline stage.

| Check | Target | Purpose | Measurable pass/fail criteria |
|---|---|---|---|
| Source connectivity and authorization | Supabase REST API | Verify the configured project and read permission. | **PASS:** authenticated request to `tbl_children` returns HTTP 2xx. **FAIL:** missing configuration, timeout, or any non-2xx response. |
| Required table/column preflight | The three in-scope tables and columns in Section 2 | Detect missing/renamed tables or fields before extracting. | **PASS:** all three tables are visible and every contracted column is available with a compatible type. **FAIL:** any table/column is missing or incompatible; do not silently fall back to `select=*`. |
| Primary-key integrity | Each extracted table's `id` | Ensure every row has a unique, non-null source identity. | **PASS:** null/missing `id` count = 0 and duplicate `id` count = 0 per table. **FAIL:** either count is greater than 0. |
| Foreign-key integrity | `tbl_assessments.child_id`, `tbl_supplements.child_id` against extracted/source children | Ensure child references resolve. | **PASS:** null/missing `child_id` count = 0 and unresolved child reference count = 0. **FAIL:** either count is greater than 0. |
| Period-boundary validation | `date_measured`, `date_administered` | Ensure rows belong to the requested month. | **PASS:** out-of-window row count = 0 using `month_start <= date < next_month_start`. **FAIL:** any row falls outside the range. |
| Exact record-count reconciliation | Each table and period | Detect incomplete pagination or extraction. | **PASS:** extracted row count equals the exact source `COUNT(*)` for the same predicates, per table; rejected count = 0 unless records are explicitly quarantined and approved. **FAIL:** count mismatch or unexplained rejected rows. |
| API response and pagination integrity | Every page for every table | Detect invalid payloads or truncated page retrieval. | **PASS:** every page is a JSON array of objects, all requests succeed, and pagination terminates after a page smaller than the configured page size. **FAIL:** malformed response, request error, or incomplete paging. |

Source counts must use the exact same table and date predicates as extraction. For `tbl_children`, count the distinct union of `child_id` values referenced by the monthly assessment and supplement windows, then count the matching child rows. On PostgREST, request an exact count (for example, `Prefer: count=exact`) and verify the returned count metadata; do not treat a page length as the total count. Capture counts immediately before and after paging; if they differ, retry the batch and fail it if the counts remain unstable.

## 4. Extraction run metadata and logging

Write one run record per extracted table and one run summary to `etl.extraction_run_logs` in the dedicated PostgreSQL ETL audit database. The audit database is separate from the health-data source and must be provisioned by the database owner before production scheduling. Run logs contain operational metadata only: never store API keys, passwords, child names, contacts, or complete source rows in the log.

| Field | Required content |
|---|---|
| `pipeline_run_id` | UUID generated once per pipeline execution and shared by its table records. |
| `target_period` | Month being processed, in `YYYY-MM` format. |
| `table_name` | Source table name for the table-level record. |
| `extraction_start_utc`, `extraction_end_utc` | UTC timestamps captured around the extraction operation. |
| `status` | `RUNNING`, `SUCCESS`, `FAILED`, or `MANUAL_REVIEW`. |
| `records_read` | Exact source count for the table and period. |
| `records_extracted` | Number of rows successfully received and staged by extraction. |
| `records_rejected` | Number of rows rejected by extraction validation; zero when no rows are rejected. |
| `validation_results` | Structured result per check, including pass/fail, expected value, observed value, and table. |
| `error_message` | Sanitized exception or failure summary; redact credentials, request authorization headers, and personal data. |

The run summary also records overall start/end timestamps, target period, final status, and a concise sanitized failure reason. Logging failure is itself a pipeline failure: do not report a run as successfully audited if its run record cannot be persisted.

## 5. Log storage, access, retention, and deletion

- **Storage:** Dedicated PostgreSQL ETL audit database, schema `etl`, table `extraction_run_logs`. It stores run metadata only, not source health records. The database owner provisions the database, table, backups, and network/access policy before enabling the scheduler.
- **Permissions:** Pipeline service account has `INSERT` and the minimum required `SELECT` permissions on run records; it has no `UPDATE`/`DELETE` permission for completed records and no access to unrelated audit tables. Database administrators have full administrative access. Authorized pipeline maintainers and MNAO reviewers receive read-only access to operational metadata. Credentials are stored in the deployment secret manager/environment, never in source control or logs.
- **Retention:** Retain run logs for 12 months. This provides a rolling year of operational troubleshooting and month-to-month audit context without keeping operational metadata indefinitely.
- **Deletion:** A database-owner-managed scheduled retention job runs monthly and permanently deletes records with `extraction_end_utc` older than 12 months. The job logs its execution and deleted-row count. Backups follow the same 12-month maximum retention where supported; expired records must age out of backups. Legal holds, if applicable, suspend deletion only for the specifically held records and require owner authorization.

## 6. Extraction data contract and schema-change handling

- **Naming convention:** Preserve PostgreSQL `snake_case` column names exactly. Standardized output names equal the source names; do not rename, normalize, impute, or derive business values during extraction.
- **Type rule:** Preserve the source type/value representation; dates use ISO `YYYY-MM-DD`, timestamps include timezone, UUIDs remain UUID values/strings, and numeric measurements retain their source precision.
- **Column selection:** Use the explicit allowlist in Section 2. Do not select all columns. Excluded parent contact fields and authentication data must not enter the extract.
- **Unexpected schema change:** Run the schema preflight before each batch. If a contracted column is missing, renamed, or has an incompatible type, fail closed, record the schema difference, alert the database owner and pipeline maintainer, and hold the batch for review. New source columns are ignored until reviewed and added to this contract. Do not silently drop required fields, coerce incompatible types, or continue with a success status.

| Source table.column | Standardized column | Source type | Target type | Mapping |
|---|---|---|---|---|
| `tbl_children.id` | `id` | `uuid` | `uuid` | 1:1 |
| `tbl_children.dob` | `dob` | `date` | `date` | 1:1 |
| `tbl_children.barangay` | `barangay` | `text` | `text` | 1:1 |
| `tbl_children.purok` | `purok` | `text` | `text` | 1:1 |
| `tbl_children.gender` | `gender` | `text` | `text` | 1:1 |
| `tbl_children.is_ip` | `is_ip` | `boolean` | `boolean` | 1:1 |
| `tbl_children.status` | `status` | `text` | `text` | 1:1 |
| `tbl_children.created_at` | `created_at` | `timestamp with time zone` | `timestamp with time zone` | 1:1 |
| `tbl_assessments.id` | `id` | `uuid` | `uuid` | 1:1 |
| `tbl_assessments.child_id` | `child_id` | `uuid` | `uuid` | 1:1 |
| `tbl_assessments.date_measured` | `date_measured` | `date` | `date` | 1:1 |
| `tbl_assessments.weight`, `height` | `weight`, `height` | `numeric(5,2)` | `numeric(5,2)` | 1:1 |
| `tbl_assessments.age_in_months` | `age_in_months` | `integer` | `integer` | 1:1 |
| `tbl_assessments.wfa_status`, `hfa_status`, `wfl_h_status` | same names | `text` | `text` | 1:1 |
| `tbl_assessments.status` | `status` | `text` | `text` | 1:1 |
| `tbl_assessments.created_at` | `created_at` | `timestamp with time zone` | `timestamp with time zone` | 1:1 |
| `tbl_supplements.id` | `id` | `uuid` | `uuid` | 1:1 |
| `tbl_supplements.child_id` | `child_id` | `uuid` | `uuid` | 1:1 |
| `tbl_supplements.supplement_type` | `supplement_type` | `text` | `text` | 1:1 |
| `tbl_supplements.dose_order`, `age_in_months` | same names | `integer` | `integer` | 1:1 |
| `tbl_supplements.date_administered` | `date_administered` | `date` | `date` | 1:1 |
| `tbl_supplements.status` | `status` | `text` | `text` | 1:1 |
| `tbl_supplements.created_at` | `created_at` | `timestamp with time zone` | `timestamp with time zone` | 1:1 |

## 7. Acceptance, review, rejection, and handover

| Decision | Criteria | Pipeline action | Responsible role |
|---|---|---|---|
| Automatic approval | Connectivity, schema, pagination, period-boundary, primary/foreign-key, and exact count checks all pass; records extracted equal exact source counts; rejected count = 0. | Mark the run `SUCCESS` and hand the unchanged, validated extract to the initial-load/data-validation stage. | Pipeline operator monitors the run; pipeline service performs the checks. |
| Manual review | A required monthly dataset or expected barangay has zero records, or records are rejected for a non-structural data issue while source access/schema/count reconciliation still work. | Mark `MANUAL_REVIEW`; hold downstream load for the affected period; record the reason; request confirmation; rerun the same monthly window after correction/approval. | Municipal Nutrition Action Officer (MNAO) confirms whether submission is complete; Barangay Nutrition Scholar (BNS) verifies/corrects source entry; pipeline operator coordinates and records disposition. |
| Rejection / hard failure | Authentication/connection fails, required schema is missing/incompatible, pagination is incomplete, exact counts mismatch, duplicate/null primary keys exist, foreign keys do not resolve, or the audit log cannot be written. | Mark `FAILED` when logging is available; stop extraction/handover, do not stage partial data, alert the pipeline maintainer and database owner, and rerun only after the failure is resolved. | Pipeline maintainer investigates code/configuration; database owner resolves grants/schema/source availability; operator tracks recovery. |

For barangay completeness review, expected barangays are taken from the agreed operational reference list for the target period. A zero-record result is reviewable only after comparing against that list; an empty table is not automatically approved as a successful month.

## 8. Problems, causes, impacts, and extraction-stage mitigations

| Problem | Cause | Impact | Mitigation |
|---|---|---|---|
| Late or missing submissions | BNS has not entered the prior month's assessments/distributions by the submission cutoff. | Monthly counts are incomplete; reports may omit a barangay or show a misleading zero. | Compare actual results with the expected barangay list; hold affected period for MNAO review; BNS confirms/corrects entry; rerun the same month after approval. |
| REST/API outage, timeout, or expired/insufficient key | Network interruption, Supabase unavailability, rotated key, or changed Row Level Security grants. | Extraction stops or may not retrieve all pages. | Use bounded timeouts and a limited retry policy for transient errors; fail and alert on persistent errors; never treat a partial response as complete; verify read grants and rerun the period. |
| Schema or API exposure change | Table/column renamed, type changed, table removed from exposed schema, or API permissions changed. | Query failure or silent omission/type drift could invalidate the batch. | Run schema preflight; fail closed; record expected/observed schema difference; database owner and maintainer review the change and update the contract before resuming. |
| Pagination truncation or duplicate page | Large result set, unstable ordering, API interruption, or paging defect. | Missing or duplicated rows and count mismatch. | Order by the primary key, track every page, reconcile exact counts, reject the run on mismatch, then retry the complete monthly window. |
| Duplicate or orphaned source identifiers | Source constraint/data integrity issue or inconsistent source snapshot during extraction. | Ambiguous joins, duplicate counts, or child records without profiles. | Check primary-key uniqueness and foreign-key resolution; reject/hold the run and request source-owner correction. Do not deduplicate or fabricate identifiers during extraction. |
| Audit database unavailable | Audit database maintenance, connectivity failure, or insufficient service-account grants. | Run outcome cannot be reliably audited. | Do not declare success or hand over the batch when the required run log cannot be persisted; alert the database owner and retry after service is restored. |

**Stage boundary:** Extraction is limited to faithful retrieval, column/type preservation, paging, and completeness/integrity checks. It does not clean, impute, standardize business values, calculate nutritional scores, or apply business transformations. Those activities belong to later validation/transformation stages.
