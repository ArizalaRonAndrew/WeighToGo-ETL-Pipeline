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