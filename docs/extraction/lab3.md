### 8. Common Extraction Problems and Mitigation
*   *Problem:* Missing Dependency Data.
    *   *Description:* The Python Scheduler triggers the pipeline, but the BNS have not yet submitted the barangay health data entries for that month.
    *   *Impact:* The extraction yields an empty dataset, causing downstream dashboards and reports to show blanks for the month.
    *   *Mitigation:* Implement a pre-extraction dependency check in Python to verify that data entries for the target month exist before initiating the full extraction script.
*   *Problem:* Network Interruption during Extraction.
    *   *Description:* Python loses connection to the Supabase/PostgreSQL database mid-extraction.
    *   *Impact:* Partial data is loaded into memory, failing the completeness validation check.
    *   *Mitigation:* The Python Scheduler will automatically discard the incomplete memory dictionary, log a connection error, and retry the extraction batch based on a predefined retry interval.