# Stage 3: Data Load Documentation

## 1. Load Source and Target Specification

| Specification | Definition |
|---|---|
| Load input | Only the single-batch handoff produced by Stage 2: the in-memory TransformationResult or its exported files under data/transformed/<YYYY-MM>/<run_id>/. The file handoff consists of dim_child.csv, fact_assessment.csv, fact_supplement.csv, fact_health_trends.csv, profiles.csv, quarantine_records.csv, validations.csv, and run_summary.csv. The loader must not re-read source tables, use raw extraction CSVs, or recalculate transformations. |
| Target system | Supabase-hosted PostgreSQL, schema etl, with the contract in [`transformation_schema.sql`](../../pipelines/transformation/transformation_schema.sql). The target Supabase project/environment must be explicitly configured; the repository does not establish whether it is the same project as the extraction source. |
| Load method | A Python-orchestrated, parameterized SQL batch job using a PostgreSQL connection. Use a single database transaction for each batch replacement and audit handoff. This repository has no implemented PostgreSQL loader or database connection for Stage 3. |
| Frequency and window | Planned monthly batch at 02:00 Asia/Manila on the 5th, after extraction and transformation complete, for the previous calendar month. The window is half-open: batch_start <= date < batch_end_exclusive. Scheduling is not configured in the repository. |
| Write method | Full replacement of the affected batch_id in dimension/fact tables using transactional DELETE plus INSERT; not a whole-table truncate and not a streaming or CDC load. Audit rows are run-scoped and written idempotently as described in Section 3. |
| Load scope | One approved transformation batch: child dimension, assessment facts, supplement facts, health-trend aggregates, and the associated transformation run/profile/quarantine audit data. Profiles and quarantine are written from Stage 2 outputs; they are not generated from raw input by the loader. |
| Handover gate | Read run_summary.csv or the equivalent TransformationResult. For operational dimension/fact rows, require status = APPROVED, a completed transformation, and matching run_id, batch_id, parent extraction ID, and batch window across the summary and each data-bearing output. validations.csv has no run/batch columns, so associate it through the same output directory. A non-approved attempt may be written to audit tables only; do not load its operational facts. |
| Database role | Use a dedicated least-privilege pipeline role over TLS. It needs schema usage, target-table SELECT for reconciliation, INSERT on the target tables, UPDATE on transformation_runs for same-attempt retries, DELETE on batch/run-scoped replacement rows, and sequence/identity privileges where required. Restrict DDL, role management, and broad administrative privileges to DBAs. Actual role names, credentials, grants, and connection settings are not configured in this repository. |
| Limitations | Transformation currently returns results in memory and can export local CSVs; export is not a database commit. The SQL file defines tables and constraints only. A scheduled loader, durable load ledger, Supabase PostgreSQL connection, role grants, and production retention job remain to be implemented/configured. |

## 2. Target Tables and Column Specification

All tables below are in the etl schema. The listed keys and constraints are taken from the SQL contract. batch_id identifies the deterministic extraction window and parent extraction run; run_id identifies one transformation attempt. Every output row is stamped with both where specified.

| Table Name | Type | Load-Critical Columns | Primary Key | Foreign Keys | Constraints | Purpose |
|---|---|---|---|---|---|---|
| etl.transformation_runs | Run-control / audit | run_id, batch_id, parent_extraction_run_id, batch_start, batch_end_exclusive, started_at_utc, ended_at_utc, status, metrics, rules_applied, validations | run_id | None | batch_id, parent_extraction_run_id, and batch dates required; status limited to APPROVED, MANUAL_REVIEW, REJECTED, FAILED; start before exclusive end; end timestamp cannot precede start. Indexed by batch/start and completed timestamp. | One row per transformation attempt. Carries the batch window, parent run, timestamps, status, metrics, rules, and validation details; must be present before rows referencing its run_id are inserted. |
| etl.dim_child | Dimension | batch_id, run_id, child_key, source_child_id, date_of_birth, barangay_name, purok_name, gender, is_ip, source_status | (batch_id, child_key) | run_id → etl.transformation_runs(run_id) | Unique (batch_id, source_child_id); required dimension fields; gender limited to MALE, FEMALE, UNKNOWN; source_status = 'ACTIVE'. | Batch-scoped child dimension used to resolve assessment and supplement facts. No child names or parent contact fields are part of this target. |
| etl.fact_assessment | Fact | batch_id, run_id, assessment_id, child_key, date_measured, assessment_month, age_months, weight_kg, height_cm, wfa_status, hfa_status, wfl_h_status | (batch_id, assessment_id) | run_id → etl.transformation_runs(run_id); (batch_id, child_key) → etl.dim_child(batch_id, child_key) | Required measures and statuses; age_months >= 0; weight_kg > 0; height_cm > 0. Indexed by batch, assessment month, and child. | Approved anthropometric assessments with standardized month, derived age, measurements, and source-supplied nutritional status labels. |
| etl.fact_supplement | Fact | batch_id, run_id, supplement_id, child_key, date_administered, supplement_month, supplement_type, dose_order, age_months | (batch_id, supplement_id) | run_id → etl.transformation_runs(run_id); (batch_id, child_key) → etl.dim_child(batch_id, child_key) | Supplement type limited to Vitamin A or Deworming; dose_order > 0; age_months >= 0. | Approved supplement administrations by child and month. |
| etl.fact_health_trends | Aggregate fact | batch_id, run_id, barangay_name, assessment_month, indicator, nutritional_status, total_count | (batch_id, barangay_name, assessment_month, indicator, nutritional_status) | run_id → etl.transformation_runs(run_id) | Indicator limited to WFA, HFA, WFL; total_count > 0. | Stage 2's pre-aggregated barangay/month/status counts for reporting. Do not recalculate these counts during load. |
| etl.transformation_profiles | Quality / audit | run_id, batch_id, table_name, column_name, issue_type, sample_values, affected_records, input_records, affected_percentage, planned_treatment, rule_id; profile_id is generated by PostgreSQL and omitted from the CSV handoff. | profile_id (identity) | run_id → etl.transformation_runs(run_id) | Required table/column/issue/treatment/rule fields; affected and input counts nonnegative; affected percentage between 0 and 100. | Persists Stage 2 profiling results and issue-level counts for audit. batch_id is present but is not a declared foreign key. |
| etl.transformation_quarantine | Restricted reject audit | run_id, batch_id, parent_extraction_run_id, table_name, source_record_id, rule_id, reason, source_record, rejected_at_utc; quarantine_id is generated by PostgreSQL and omitted from the CSV handoff. | quarantine_id (UUID default) | run_id → etl.transformation_runs(run_id) | Required batch, parent run, source table, rule, reason, and source-record payload fields. Indexed by batch/table and rejection timestamp. | Persists only the quarantine rows handed over by Stage 2, including reason and source record for authorized review. This table can contain sensitive child/health data and requires tighter access than aggregate facts. |

The transformed data files do not include a separate load-run table. The schema also does not declare a unique constraint on transformation_runs.batch_id; use its batch index for lookup, not as proof that a batch has or has not been loaded.

## 3. Load Strategy and Rules

| Target Table | Load Type (Full/Incremental) | Write Logic (Upsert/Insert) | Match Key | On Failure |
|---|---|---|---|---|
| etl.transformation_runs | Incremental by transformation attempt | Insert; on retry of the same run_id, update that row's handoff metadata rather than create a second attempt. Do not overwrite a different run_id. | run_id | Roll back the transaction. Record the load error in the external job log; retain the transformation handoff for retry. |
| etl.dim_child | Full replacement scoped to batch_id | Delete existing rows for the batch, then insert the complete handed-over dimension. | (batch_id, child_key); also enforce unique (batch_id, source_child_id) | Roll back the whole transaction, including deletes and inserts. |
| etl.fact_assessment | Full replacement scoped to batch_id | Delete existing rows for the batch, then insert the complete handed-over fact set. | (batch_id, assessment_id) | Roll back the whole transaction. |
| etl.fact_supplement | Full replacement scoped to batch_id | Delete existing rows for the batch, then insert the complete handed-over fact set. | (batch_id, supplement_id) | Roll back the whole transaction. |
| etl.fact_health_trends | Full replacement scoped to batch_id | Delete existing rows for the batch, then insert the complete pre-aggregated set. | (batch_id, barangay_name, assessment_month, indicator, nutritional_status) | Roll back the whole transaction. |
| etl.transformation_profiles | Incremental by transformation attempt | Delete prior profile rows for the same run_id, then insert the handed-over rows for that attempt. Keep rows for earlier run IDs. | run_id for retry replacement; generated profile_id for stored rows | Roll back the whole transaction. |
| etl.transformation_quarantine | Incremental by transformation attempt | Delete prior quarantine rows for the same run_id, then insert the handed-over rows for that attempt. Keep rows for earlier run IDs. | run_id for retry replacement; generated quarantine_id for stored rows | Roll back the whole transaction. |

The batch identifier is generated deterministically from the parent extraction run ID and the half-open date window; a new transformation attempt receives a different run_id. A rerun of an approved batch therefore replaces that entire batch in the dimension/fact tables, rather than appending duplicates. Audit detail is keyed to the attempt so earlier attempts remain reviewable. Before any delete, validate identity fields in the run summary and every data-bearing file; associate validations.csv with that handoff by its output directory because its rows have no run or batch IDs.

Load order within one transaction:

1. Validate and write/update the transformation_runs row for the handed-over run_id.
2. Delete the batch's existing assessment, supplement, and health-trend rows before changing its dimension; these facts reference the dimension.
3. Delete the batch's existing dim_child rows.
4. Insert the complete new dimension, then the assessment and supplement facts.
5. Insert the complete health-trend aggregates without recalculating them.
6. Replace profiles and quarantine rows for the current run_id; omit generated profile_id and quarantine_id columns so PostgreSQL assigns them.
7. Run the post-load checks in Section 5, then commit only if every critical check passes.

For MANUAL_REVIEW or REJECTED transformation outcomes, persist the run metadata and available profile/quarantine audit outputs only; do not replace the approved dimension/fact batch. Any SQL error, failed foreign key, count mismatch, or failed critical reconciliation must roll back all writes in the transaction. The target schema has no load-status ledger or content checksum, so a separate durable load log is required to distinguish a committed load from a transformation that was merely APPROVED. Until that exists, a retry must query the target and use the batch-scoped replacement behavior rather than assume that a prior attempt did not commit.

## 4. Pre-Load Validation Checks

| Check Name | Target | Purpose | Validation Criteria | Severity (Critical/Non-critical) |
|---|---|---|---|---|
| Target connection and TLS | Supabase PostgreSQL | Confirm availability and secure connectivity before opening a load transaction. | Connection succeeds using configured credentials and TLS; no credentials are printed or stored in handoff files. | Critical |
| Target schema and contract | etl schema and all seven target tables | Prevent incompatible writes or silent schema drift. | Schema exists; expected columns, types, keys, checks, and foreign keys match the deployed contract; schema deployment version is recorded. | Critical |
| Handover completeness | Transformation output directory or in-memory result | Ensure the loader consumes a complete Stage 2 result, not a partial file set. | All expected handoff components exist; each CSV parses with the expected header, including empty-file headers; run_summary.csv contains exactly one run summary. | Critical |
| Transformation approval | run_summary.csv / TransformationResult | Enforce Stage 2 acceptance before loading reportable facts. | status = APPROVED, ended_at_utc is present, and no critical validation has failed. Non-approved runs are audit-only. | Critical |
| Handoff identity and window | Data output files and run summary | Prevent mixing batches or loading dates outside the approved window. | run_id, batch_id, and window agree across the summary and every row that carries those fields; associate validations.csv with the same run through its output directory and summary because validation rows do not carry run or batch IDs. batch_start < batch_end_exclusive; fact dates fall within the half-open window. | Critical |
| Handoff reconciliation | Run summary, validation, and output files | Detect missing or altered transformation output. | Recompute file row counts and compare with Stage 2 metrics and validations; each source table satisfies records_read = records_output + records_rejected. | Critical |
| Duplicate batch / retry state | Target batch rows and durable load log | Avoid duplicate writes and unsafe retry decisions. | For the same batch_id, verify the prior load outcome and input identity. If outcome is uncertain, reconcile target state before retry; a matching replay may safely use full batch replacement. | Critical |
| Target privileges and constraints | Pipeline role and etl tables | Catch missing grants or disabled constraints before changing data. | Role can select for validation, insert, and delete only required rows; foreign keys and check constraints are enabled; no DDL/admin grant is required. | Critical |
| Input row-key uniqueness | Handoff datasets | Detect malformed output before target constraints reject it. | No duplicate dimension, assessment, supplement, or aggregate match keys within the current batch; profile/quarantine rows have valid run IDs. | Critical |
| Empty batch review | Handoff counts | Avoid treating an unexpected empty month as a successful load. | If all business outputs are empty, require an explicit expected-empty approval in the operational load log; otherwise hold for review. | Non-critical |

## 5. Post-Load Validation and Reconciliation

Run these checks inside the load transaction before COMMIT. A critical failure means ROLLBACK; do not report the batch as loaded.

| Check Name | Target | Purpose | Validation Criteria | Severity |
|---|---|---|---|---|
| Record reconciliation | Each target table for the batch/current run | Confirm that PostgreSQL received every row from the approved handoff. | For each output file, inserted row count equals parsed handoff row count; target count for the batch/run equals the expected count after replacement. | Critical |
| Key uniqueness | dim_child, fact_assessment, fact_supplement, fact_health_trends | Ensure no duplicate business rows were introduced. | Duplicate count for each declared primary key and dim_child(batch_id, source_child_id) is zero. | Critical |
| Referential integrity | Run, dimension, and fact tables | Ensure every fact belongs to the correct run and same-batch dimension. | Every fact run_id resolves to transformation_runs; every fact (batch_id, child_key) resolves to dim_child; orphan count is zero. | Critical |
| Constraint and null validation | All loaded tables | Confirm database-enforced contract rules accepted the batch. | No rejected insert; required values are non-null; measurements, ages, dose orders, statuses, and indicator values satisfy the schema checks. | Critical |
| Assessment amount reconciliation | etl.fact_assessment and etl.fact_health_trends | Ensure each accepted assessment contributes one count to each of the three passed-through indicators. | SUM(fact_health_trends.total_count) = 3 * COUNT(fact_assessment) for the batch. | Critical |
| Supplement count reconciliation | etl.fact_supplement | Detect missing or duplicated supplement rows. | Target count for the batch equals fact_supplement.csv row count; all supplement rows are in the declared window. | Critical |
| Batch identity and window | All batch-scoped target tables | Verify no rows from another batch or run leaked into the replacement. | Every loaded row has the expected batch_id and current run_id; all dates are within [batch_start, batch_end_exclusive). | Critical |
| Audit completeness | etl.transformation_runs, etl.transformation_profiles, etl.transformation_quarantine | Preserve lineage and quality evidence for the attempt. | Run row matches the summary; profile and quarantine counts match their handoff files; rejected input rows retain their Stage 2 reason/rule and source-record reference. | Critical |
| Commit confirmation | PostgreSQL transaction and durable load log | Establish whether the load completed and make retries safe. | Commit succeeds and the external load log records the committed batch, row counts, and timestamp. If the connection drops during commit, mark outcome unknown and reconcile before retry. | Critical |

## 6. Load Metadata and Log Specification

The transformation handoff provides run/batch context and transformation metrics. The target schema has no dedicated load-run table or load timestamps; persist load-specific fields in a protected structured job log or add a separately approved load ledger before production scheduling. Do not imply that transformation started_at_utc is the load start time.

| Field | Purpose | Example |
|---|---|---|
| load_run_id | Unique identifier for one database load attempt. | LOAD_20261105_020012Z_01 |
| run_id | Identifies the Stage 2 transformation attempt being loaded. | 5c89450a-ce48-40ec-8b19-206373f74f3b |
| batch_id | Idempotency and reconciliation key for the extraction window. | e2e8a405-eae1-5d11-a54d-6921077c8f2a |
| parent_extraction_run_id | Lineage pointer to the Stage 1 handoff. | EXT_<uuid> |
| batch_start, batch_end_exclusive | Exact half-open data window being loaded. | 2026-10-01, 2026-11-01 |
| load_start_ts, load_end_ts | UTC timestamps for load duration and incident analysis. | 2026-11-05T02:00:12Z, 2026-11-05T02:00:19Z |
| status | Load outcome, separate from the transformation status. | COMMITTED, ROLLED_BACK, AUDIT_ONLY, FAILED, UNKNOWN |
| records_received | Number of data rows parsed from each transformation output file. | {"dim_child": 120, "fact_assessment": 830} |
| records_inserted | Number of rows written per target table after replacement. | {"etl.fact_assessment": 830} |
| records_rejected | Rows not loaded because the transformation quarantined them or load validation rejected them. Record counts/reasons, not sensitive payloads, in the load log. | {"transformation_quarantine": 4} |
| validation_results | Check name, severity, result, and safe diagnostic detail. | {"referential_integrity": "PASS"} |
| error_code, error_summary | Support diagnosis without recording credentials or full sensitive rows. | 23503, Foreign key validation failed for batch |
| handoff_location | Trace the specific Stage 2 output directory or immutable object reference. | data/transformed/2026-10/<run_id>/ |

These fields provide lineage from load attempt to transformation and extraction, document counts and decisions, and establish whether a retry is safe. Keep them structured and correlate them by load_run_id, run_id, and batch_id. Never log connection strings, keys, full rejected records, child names, or parent contact details.

## 7. Log Retention, Rejected Data, and Access

- *Retention period:* Retain load logs, transformation run metadata, profiles, and quarantine records for 12 months, consistent with the Stage 2 audit policy. Confirm applicable municipal and health-data retention requirements with the data owner before production use.
- *Storage location:* Store database audit data in the restricted Supabase etl schema. Store load-attempt events in a protected structured logging destination or a separately approved load ledger. Local CSV handoffs under data/transformed/ are temporary operational artifacts, are git-ignored, and are not a durable audit store.
- *Rejected data:* The loader must consume only quarantine_records.csv from the transformation handoff. Preserve rejection rule, reason, source table, source-record identifier, and batch/run lineage in the restricted quarantine target. Do not create a second copy from raw extraction data, and do not write full health payloads into general application logs.
- *Access permissions:* The pipeline role receives only the table-level privileges required to load and reconcile. Authorized pipeline maintainers and designated MNAO reviewers receive read-only access to audit/quarantine data as needed. Limit quarantine access more tightly than aggregate reporting data. DBAs alone manage DDL, roles, backups, and retention.
- *Deletion rules:* Run a monthly, database-owner-managed retention process to remove expired rows in dependency-safe order. Delete assessment, supplement, and trend facts before their referenced child dimensions; delete facts, dimensions, profiles, and quarantine rows before their referenced run rows. Do not delete data still within the approved retention period. Remove local handoff files only after successful load and required review/retention copying, according to the approved operating procedure.
- *Status:* The 12-month policy is documented by the transformation stage, but the schema does not create roles, grants, a scheduler, or a retention job. These controls must be configured and tested before production.

## 8. Load Acceptance, Rollback, and Completion Rules

| Overall Condition | Acceptance Decision | Pipeline Action |
|---|---|---|
| Target/schema and handoff prechecks pass; Stage 2 status is APPROVED; all critical post-load checks pass; transaction commits. | Accept | Record COMMITTED and counts in the durable load log; expose the batch to downstream reporting; return success. |
| Stage 2 status is MANUAL_REVIEW, a warning requires review, an expected-empty batch is unconfirmed, or the target's prior commit outcome is uncertain. | Hold for manual review | Do not replace operational batch facts. Preserve/record available run, profile, and quarantine audit outputs; notify the operator/data owner; resume only with documented approval or after resolving the uncertain outcome. |
| Stage 2 status is REJECTED`/FAILED`, handoff/schema identity is invalid, a critical pre/post check fails, or a database statement fails. | Reject / fail | Do not publish the batch. Roll back the transaction, record a safe failure summary, alert the maintainer, and retain the handoff for investigation or corrected rerun. |

| Condition Class | Conditions | Required Decision |
|---|---|---|
| Automatic Approval | Handoff is complete and consistent; transformation status is APPROVED; all required target checks pass; batch-scoped replacement, audit writes, and reconciliations complete in one transaction. | Commit and record COMMITTED; only after commit is the batch complete. |
| Manual Review | Transformation status is MANUAL_REVIEW; any operator approval is outstanding; all business rows are empty without an expected-empty approval; or a connection loss leaves commit outcome unknown. | Keep facts unpublished. Record AUDIT_ONLY`/UNKNOWN` as appropriate and require a named reviewer or reconciliation before proceeding. |
| Rejection / Failure | Transformation status is REJECTED or FAILED; contract mismatch, missing files, inconsistent IDs, duplicate match keys, failed FK/check, reconciliation mismatch, insufficient privilege, or SQL/connection failure before known commit. | Roll back all uncommitted changes, log ROLLED_BACK`/FAILED`, alert the owner, and do not report successful completion. |

*Rollback and completion:* A load is complete only after the transaction commit and durable success logging. Keep delete-and-insert replacement and validation in the same transaction so failures cannot expose a partial batch. If the connection fails while commit status is unknown, do not blindly rerun; inspect the target and load ledger, reconcile by batch_id and run_id, then retry the idempotent batch replacement if necessary. A committed batch later found incorrect requires a controlled corrective batch/replacement, not an untracked partial delete.

## 9. Common Load Problems and Mitigation

| Problem | Possible Cause | Impact | Mitigation |
|---|---|---|---|
| Duplicate rows after rerun | Append-only inserts, an unsafe retry after an uncertain commit, or inconsistent batch_id`/match keys. | Duplicate dimensions/facts or primary-key violations; inflated reports if constraints are absent. | Use the deterministic batch_id`; replace the entire affected batch transactionally; check match-key uniqueness and reconcile prior commit state before retry. |
| Foreign key violations | Dimension not loaded first; fact references a child absent from the same batch; run row missing for run_id. | Transaction fails or leaves incomplete lineage if writes are not atomic. | Insert/update run metadata first, then dimension, then facts; validate same-batch child references; preserve/enforce PostgreSQL foreign keys and roll back on failure. |
| Partial load | Timeout, connection interruption, statement failure, or commits split across tables. | Facts and aggregates may disagree or only some tables may reflect the batch. | Use one transaction for replacement and post-load checks; retry only after confirming commit state; log unknown commit outcomes explicitly. |
| Handoff file missing, truncated, or from another run | Interrupted Stage 2 export, wrong output directory, or files combined from separate attempts. | Incomplete or mixed data can overwrite a valid batch. | Require all handoff files and headers; verify row counts and identical run_id, batch_id, and window before opening the transaction. |
| Schema or data-type mismatch | SQL contract not applied, changed column type, malformed CSV values, or target schema drift. | Inserts fail or values are misinterpreted. | Preflight target schema; use explicit column lists and typed parameterized inserts/COPY; stop on mismatch rather than coercing silently. |
| Check-constraint violation | Invalid gender/status/indicator/supplement type, non-positive measure/count, or negative age/dose order in handoff. | Transaction is rejected and the batch cannot be accepted. | Validate Stage 2 contract before load, keep target constraints enabled, report offending table/key without logging sensitive payload, and return the record to transformation review. |
| Supabase connection or pool exhaustion | Incorrect endpoint/credentials, network/TLS issue, connection limits, or concurrent scheduled retries. | Load cannot start or may time out with uncertain commit status. | Use a bounded schedule with one active load per batch, TLS, a small connection pool, timeouts, and controlled retries; reconcile target state after ambiguous commit failure. |
| Insufficient privileges | Pipeline role lacks schema usage, DELETE`/INSERT`/`SELECT`, or identity-sequence access. | Transaction fails; operational workaround with an over-privileged account increases risk. | Provision and test a least-privilege role before deployment; request DBA-managed grants rather than broadening runtime access. |
| Batch overwrite with changed handoff | Same deterministic batch ID is regenerated from corrected or non-identical source data. | Previously accepted rows may be replaced by a different result with no clear audit trail. | Compare parent run/window and persisted handoff identity; retain run-scoped audit history and load checksums in the durable load ledger; require authorized correction approval. |
| Sensitive rejected data exposed | Quarantine or local CSVs copied into general logs, shared folders, or unrestricted backups. | Unauthorized disclosure of child and health information. | Restrict quarantine and local handoff permissions, redact log detail, encrypt storage/transit, enforce retention/deletion, and review access regularly. |