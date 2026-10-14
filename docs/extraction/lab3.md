### 7. Extraction Acceptance and Handover Rules
*   *Automatic Approval:* If Python successfully connects to Supabase/PostgreSQL and the extracted record counts match the source batch counts without any missing identifiers, the data is *APPROVED*.
    *   Pipeline Action: Python automatically proceeds to the "Initial Load" step, inserting this raw data into temporary staging tables inside Supabase PostgreSQL.
*   *Manual Review:* If the selected monthly processing period yields 0 records for a specific barangay.
    *   Pipeline Action: Hold pipeline execution and flag the Municipal Nutrition Action Officers (MNAO) to verify if the BNS missed their data entry window.
*   *Rejection or Failure:* If the Python script fails to authenticate with Supabase/PostgreSQL.
    *   Pipeline Action: Stop the pipeline and log a critical failure.
*   *Handover:* Extracted raw health data records are staged in PostgreSQL for the subsequent Data Validation step.