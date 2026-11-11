# Synthetic pipeline demo walkthrough

This walkthrough prepares a repeatable demonstration of the current
transformation pipeline. All names and IDs in the inputs are computer-generated.
The demo does not connect to Supabase or write to PostgreSQL.

## What is included

- `demo/fixtures/tbl_children.csv`: synthetic child dimension source rows.
- `demo/fixtures/tbl_assessments.csv`: synthetic monthly measurements and
  supplied nutritional status labels.
- `demo/fixtures/tbl_supplements.csv`: synthetic supplement events.
- `scripts/run_demo.py`: runs one clean batch and eight isolated validation
  scenarios, checks expected outcomes, and saves each run's CSV reports.

The CSV columns follow the current extraction contract. Events fall within
October 2026 (`2026-10-01` inclusive to `2026-11-01` exclusive). The child IDs
in assessments and supplements match the child input rows. The runner fixes the
as-of date to October 31, 2026 so future-date checks are reproducible.

## Before the presentation

1. Open a terminal at the repository root.
2. Confirm Python is available:

   ```powershell
   python --version
   ```

3. Run the demonstration:

   ```powershell
   python -m scripts.run_demo
   ```

   It uses only Python's standard library and the existing transformation
   module; no Supabase credentials or additional package installation is
   needed.

4. Confirm the last line says `DEMO PASSED`. The runner stops with an assertion
   error if an expected status or quarantine rule does not occur.
5. Open `data/demo-output/clean/` and show `dim_child.csv`,
   `fact_assessment.csv`, `fact_supplement.csv`, `fact_health_trends.csv`,
   `validations.csv`, and `run_summary.csv`.
6. Open each validation scenario folder under `data/demo-output/` and inspect
   `quarantine_records.csv`, `validations.csv`, and `run_summary.csv`. Those
   outputs are generated locally and are ignored by Git.



From the repository root, run:

```powershell
python -m unittest pipelines.transformation.test_health_trends
python -m unittest pipelines.extractions.test_extractor
```

The transformation tests cover processing rules; extractor tests use mocked
HTTP responses. The demo itself exercises the transformation using local
synthetic CSVs. Do not describe these as proof of a live Supabase extraction or
database load.



## If something fails

1. Check that the terminal is at the repository root.
2. Confirm the three CSV fixture files are present and retain their headers.
3. Read the first assertion or traceback from the runner; it identifies the
   scenario that did not match the current transformation behavior.
4. Run the two unit-test commands above and report any failure rather than
   claiming the demo passed.
