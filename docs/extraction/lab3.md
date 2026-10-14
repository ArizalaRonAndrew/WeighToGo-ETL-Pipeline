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