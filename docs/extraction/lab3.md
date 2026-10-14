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