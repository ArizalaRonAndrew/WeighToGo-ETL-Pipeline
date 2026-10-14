WeighToGo — Stage 1: Data Extraction Documentation

# Stage 1: Data Extraction Documentation

### 1. Data Source and Extraction Specification
*   *Source System:* WeighToGo System.
*   *Purpose:* To continuously log operational child anthropometric assessments and vitamin and deworming distributions directly into the primary OLTP tables.
*   *Source Database:* Supabase/PostgreSQL.
*   *Extraction Method:* 
    *   *Tool:* Python.
    *   *Orchestration:* Python Scheduler.
    *   *Logic:* Incremental batch extraction based on the selected monthly processing period. Python connects to the Supabase/PostgreSQL database and retrieves the required records into memory using standard dictionaries.
*   *Extraction Scope:* Raw child profiles, anthropometric assessments, and supplement distribution data grouped by month and barangay.
*   *Source Limitations and Assumptions:* The pipeline execution is dependent on the Barangay Nutrition Scholars (BNS) submitting the barangay health data entries prior to the pipeline running.

### 2. Source Tables and Column Specification
The extraction focuses on three primary operational tables from the Supabase/PostgreSQL database.

*Table 1: children*
*   *Purpose:* Stores child demographic profiles.
*   *Key Columns & Types:* id (uuid), name (text), dob (date), barangay (text), purok (text), gender (text).
*   *Identifiers:* Primary Key is id.
*   *Relationships:* Referenced by assessment.child_id and supplements.child_id.
*   *Reason for Inclusion:* Required for verifying child demographic profiles and grouping metrics geographically by barangay.

*Table 2: assessment*
*   *Purpose:* Records child anthropometric assessments.
*   *Key Columns & Types:* id (uuid), child_id (uuid), date_measured (date), weight (numeric), height (numeric), age_in_months (integer), hfa_status (text), wfa_status (text), wfl_h_status (text).
*   *Identifiers:* Primary Key is id. Foreign Key child_id references children.id.
*   *Reason for Inclusion:* Provides the raw measurement data needed to compute WHO z-scores, evaluate nutritional statuses, and aggregate malnutrition summaries.

*Table 3: supplements*
*   *Purpose:* Logs vitamin and deworming supplement distributions.
*   *Key Columns & Types:* id (uuid), child_id (uuid), supplement_type (text), dose_order (integer), age_in_months (integer), date_administered (date).
*   *Identifiers:* Primary Key is id. Foreign Key child_id references children.id.
*   *Reason for Inclusion:* Essential for tracking vitamin and deworming compliance.

### 3. Extraction Validation and Data Quality Checks
These checks verify the extraction's success before Python inserts the raw data into temporary staging tables inside Supabase PostgreSQL.

*   *Check 1: Source Connection Accessibility*
    *   *Target:* Supabase/PostgreSQL Database.
    *   *Purpose:* Ensure the Python script can successfully connect to the operational source.
    *   *Validation Criteria:* A successful connection and authentication response from the database prior to executing extraction queries.
*   *Check 2: Record Count Completeness*
    *   *Target:* children, assessment, and supplements batch extraction results.
    *   *Purpose:* Verify that all records for the selected monthly processing period were extracted.
    *   *Validation Criteria:* The total count of extracted dictionaries in Python memory must match the COUNT() query result of the target batch in PostgreSQL.
*   *Check 3: Required Identifiers Check*
    *   *Target:* id and child_id columns across extracted datasets.
    *   *Purpose:* Ensure relational integrity is maintained during the extraction into memory.
    *   *Validation Criteria:* 0 NULL values in Primary Key (id) and Foreign Key (child_id) fields.

### 4. Extraction Metadata and Log Specification
To monitor the monthly batch processing managed by the Python Scheduler, the following metadata will be logged:

| Field | Purpose | Example Value |
| :--- | :--- | :--- |
| *Pipeline Run ID* | Unique identifier for the batch execution | batch_run_20261014_01 |
| *Target Period* | The selected monthly processing period | October 2026 |
| *Table Name* | Identifies which dataset is being extracted | assessment |
| *Extraction Start/End* | Timestamps to monitor extraction duration | 2026-10-14 13:47:00 |
| *Extraction Status* | Indicates success or failure of the stage | SUCCESS |
| *Records Extracted* | Number of raw records loaded into Python memory | 1,250 |
| *Error Message* | Captures failure reasons | Connection timeout to Supabase |

### 5. Log Retention and Access
*   *Log Retention Period:* Logs will be retained for 12 months to allow year-over-year operational pipeline troubleshooting, aligning with the system's yearly nutritional status comparisons.
*   *Storage Location:* A dedicated operational logging table within the WeighToGo Supabase/PostgreSQL database.
*   *Access Permissions:* Restricted to Database Administrators and the developers managing the Python Scheduler.

### 6. Extraction Data Contract and Naming Convention
*   *Required Schema & Naming Convention:* The extracted data will perfectly mirror the source schema using snake_case naming conventions for all columns (e.g., date_measured, age_in_months, hfa_status). 
*   *Schema Consistency:* Because both the Source and Destination share the exact same database platform (WeighToGo Supabase/PostgreSQL), extraction mappings are strictly 1:1. 

| Source Column | Standardized Column | Source Type | Target Type | Mapping Type |
| :--- | :--- | :--- | :--- | :--- |
| child_id | child_id | uuid | uuid | 1:1 Pass-through |
| date_measured | date_measured | date | date | 1:1 Pass-through |
| age_in_months | age_in_months | integer | integer | 1:1 Pass-through |

### 7. Extraction Acceptance and Handover Rules
*   *Automatic Approval:* If Python successfully connects to Supabase/PostgreSQL and the extracted record counts match the source batch counts without any missing identifiers, the data is *APPROVED*.
    *   Pipeline Action: Python automatically proceeds to the "Initial Load" step, inserting this raw data into temporary staging tables inside Supabase PostgreSQL.
*   *Manual Review:* If the selected monthly processing period yields 0 records for a specific barangay.
    *   Pipeline Action: Hold pipeline execution and flag the Municipal Nutrition Action Officers (MNAO) to verify if the BNS missed their data entry window.
*   *Rejection or Failure:* If the Python script fails to authenticate with Supabase/PostgreSQL.
    *   Pipeline Action: Stop the pipeline and log a critical failure.
*   *Handover:* Extracted raw health data records are staged in PostgreSQL for the subsequent Data Validation step.

### 8. Common Extraction Problems and Mitigation
*   *Problem:* Missing Dependency Data.
    *   *Description:* The Python Scheduler triggers the pipeline, but the BNS have not yet submitted the barangay health data entries for that month.
    *   *Impact:* The extraction yields an empty dataset, causing downstream dashboards and reports to show blanks for the month.
    *   *Mitigation:* Implement a pre-extraction dependency check in Python to verify that data entries for the target month exist before initiating the full extraction script.
*   *Problem:* Network Interruption during Extraction.
    *   *Description:* Python loses connection to the Supabase/PostgreSQL database mid-extraction.
    *   *Impact:* Partial data is loaded into memory, failing the completeness validation check.
    *   *Mitigation:* The Python Scheduler will automatically discard the incomplete memory dictionary, log a connection error, and retry the extraction batch based on a predefined retry interval.