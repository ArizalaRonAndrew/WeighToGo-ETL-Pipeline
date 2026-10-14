### 6. Extraction Data Contract and Naming Convention
*   *Required Schema & Naming Convention:* The extracted data will perfectly mirror the source schema using snake_case naming conventions for all columns (e.g., date_measured, age_in_months, hfa_status). 
*   *Schema Consistency:* Because both the Source and Destination share the exact same database platform (WeighToGo Supabase/PostgreSQL), extraction mappings are strictly 1:1. 

| Source Column | Standardized Column | Source Type | Target Type | Mapping Type |
| :--- | :--- | :--- | :--- | :--- |
| child_id | child_id | uuid | uuid | 1:1 Pass-through |
| date_measured | date_measured | date | date | 1:1 Pass-through |
| age_in_months | age_in_months | integer | integer | 1:1 Pass-through |