import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipelines.transformation.health_trends import (
    save_transformation_result,
    transform_batch,
    transform_health_trends,
)


def child(child_id="child-1", **overrides):
    row = {
        "id": child_id,
        "name": "Test Child",
        "dob": "2024-01-15",
        "barangay": " Barangay 1 ",
        "purok": "purok a",
        "gender": "boy",
        "is_ip": False,
        "status": "active",
        "created_at": "2024-01-01T00:00:00Z",
        "parent_contact": "must-not-be-in-quarantine",
    }
    row.update(overrides)
    return row


def assessment(assessment_id="assessment-1", **overrides):
    row = {
        "id": assessment_id,
        "child_id": "child-1",
        "date_measured": "2026-10-14",
        "weight": 12.345,
        "height": 90.126,
        "age_in_months": 32,
        "wfa_status": "Normal",
        "hfa_status": "Stunted",
        "wfl_h_status": "Normal",
        "status": "active",
        "created_at": "2026-10-14T12:00:00Z",
    }
    row.update(overrides)
    return row


def supplement(supplement_id="supplement-1", **overrides):
    row = {
        "id": supplement_id,
        "child_id": "child-1",
        "supplement_type": "Vitamin A",
        "dose_order": 1,
        "age_in_months": 32,
        "date_administered": "2026-10-14",
        "status": "active",
        "created_at": "2026-10-14T12:00:00Z",
    }
    row.update(overrides)
    return row


def run_transform(assessments=None, children=None, supplements=None, **kwargs):
    return transform_batch(
        [assessment()] if assessments is None else assessments,
        [child()] if children is None else children,
        [supplement()] if supplements is None else supplements,
        parent_extraction_run_id="EXT_TEST",
        batch_start="2026-10-01",
        batch_end="2026-11-01",
        as_of_date=date(2026, 10, 31),
        **kwargs,
    )


class TestTransformHealthTrends(unittest.TestCase):
    def test_creates_dimension_facts_and_monthly_indicator_aggregates(self):
        result = run_transform(
            assessments=[
                assessment(),
                assessment(
                    "assessment-2",
                    wfa_status="Underweight",
                    hfa_status="Stunted",
                    wfl_h_status="Normal",
                ),
            ]
        )

        self.assertEqual(result.status, "APPROVED")
        self.assertEqual(len(result.dim_child), 1)
        self.assertEqual(result.dim_child[0]["barangay_name"], "BARANGAY 1")
        self.assertEqual(result.dim_child[0]["gender"], "MALE")
        self.assertEqual(len(result.fact_assessment), 2)
        self.assertEqual(result.fact_assessment[0]["weight_kg"].to_eng_string(), "12.35")
        self.assertEqual(result.fact_assessment[0]["age_months"], 32)
        wfa_normal = next(
            row for row in result.fact_health_trends
            if row["indicator"] == "WFA"
            and row["nutritional_status"] == "NORMAL"
        )
        self.assertEqual(wfa_normal["total_count"], 1)
        self.assertEqual(
            sum(row["total_count"] for row in result.fact_health_trends),
            2 * 3,
        )

    def test_missing_nutritional_status_is_preserved_as_unclassified(self):
        result = run_transform(
            assessments=[
                assessment(wfa_status=None, hfa_status="", wfl_h_status="Normal")
            ]
        )
        self.assertIn(
            ("WFA", "UNCLASSIFIED"),
            {
                (row["indicator"], row["nutritional_status"])
                for row in result.fact_health_trends
            },
        )

    def test_latest_duplicate_is_kept_and_older_row_quarantined(self):
        result = run_transform(assessments=[
            assessment(created_at="2026-10-14T10:00:00Z", weight=10),
            assessment(created_at="2026-10-14T12:00:00Z", weight=11),
        ])
        self.assertEqual(len(result.fact_assessment), 1)
        self.assertEqual(result.fact_assessment[0]["weight_kg"].to_eng_string(), "11.00")
        self.assertEqual(len(result.quarantine_records), 1)
        self.assertEqual(result.quarantine_records[0]["rule_id"], "C-04")
        self.assertEqual(
            result.metrics["tbl_assessments"],
            {"records_read": 2, "records_output": 1, "records_rejected": 1},
        )

    def test_duplicate_with_tied_created_at_is_quarantined(self):
        row = assessment()
        result = run_transform(assessments=[row, dict(row)])
        self.assertEqual(result.fact_assessment, [])
        self.assertEqual(len(result.quarantine_records), 2)
        self.assertEqual(
            {item["reason"] for item in result.quarantine_records},
            {"duplicate id has tied latest created_at values"},
        )

    def test_non_active_record_is_quarantined_and_not_aggregated(self):
        result = run_transform(
            assessments=[assessment(status="reject")],
            supplements=[],
        )
        self.assertEqual(result.fact_assessment, [])
        self.assertEqual(result.quarantine_records[0]["rule_id"], "B-03")
        self.assertEqual(result.status, "MANUAL_REVIEW")

    def test_negative_measurement_is_quarantined_and_profiled(self):
        result = run_transform(
            assessments=[assessment(weight=-1)],
            supplements=[],
        )
        self.assertEqual(result.fact_assessment, [])
        self.assertEqual(result.quarantine_records[0]["rule_id"], "C-02")
        profile = next(
            item for item in result.profiles
            if item["rule_id"] == "C-02"
        )
        self.assertEqual(profile["affected_percentage"], 100)
        self.assertEqual(profile["sample_values"], [-1])
        self.assertEqual(result.status, "MANUAL_REVIEW")

    def test_future_supplement_date_is_quarantined(self):
        result = run_transform(
            assessments=[],
            supplements=[supplement(date_administered="2026-11-01")],
        )
        self.assertEqual(result.fact_supplement, [])
        self.assertEqual(result.quarantine_records[0]["rule_id"], "C-03")

    def test_orphan_assessment_is_quarantined(self):
        result = run_transform(
            assessments=[assessment(child_id="missing-child")],
            supplements=[],
        )
        self.assertEqual(result.fact_assessment, [])
        self.assertEqual(result.quarantine_records[0]["rule_id"], "B-01")

    def test_quarantine_redacts_parent_contact_fields(self):
        result = run_transform(
            children=[child(status="reject")],
            assessments=[],
            supplements=[],
        )
        quarantined_child = result.quarantine_records[0]["source_record"]
        self.assertNotIn("name", quarantined_child)
        self.assertNotIn("parent_contact", quarantined_child)
        self.assertNotIn("parent_name", quarantined_child)

    def test_rerun_has_same_batch_id_and_new_attempt_run_id(self):
        first = run_transform()
        second = run_transform()
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertNotEqual(first.run_id, second.run_id)

    def test_all_source_tables_reconcile_to_output_plus_rejected(self):
        result = run_transform(
            assessments=[assessment(weight=-2)],
            children=[child()],
            supplements=[supplement(status="reject")],
        )
        for metrics in result.metrics.values():
            self.assertEqual(
                metrics["records_read"],
                metrics["records_output"] + metrics["records_rejected"],
            )
        self.assertTrue(
            all(item["passed"] for item in result.validations
                if item["check_name"] == "record reconciliation")
        )

    def test_exactly_one_percent_rejections_requires_manual_review(self):
        assessments = [
            assessment(f"assessment-{index}")
            for index in range(98)
        ]
        assessments.append(assessment("bad-assessment", weight=-1))
        result = run_transform(
            assessments=assessments,
            supplements=[],
        )
        self.assertEqual(result.status, "MANUAL_REVIEW")
        self.assertEqual(
            sum(m["records_read"] for m in result.metrics.values()),
            100,
        )
        self.assertEqual(
            sum(m["records_rejected"] for m in result.metrics.values()),
            1,
        )

    def test_missing_required_column_fails_batch(self):
        row = assessment()
        del row["weight"]
        result = run_transform(assessments=[row], supplements=[])

        schema_check = next(
            check for check in result.validations
            if check["check_name"] == "required source columns"
            and check["table_name"] == "tbl_assessments"
        )
        self.assertFalse(schema_check["passed"])
        self.assertEqual(result.status, "REJECTED")

    def test_saves_transformation_outputs_and_review_details_to_csv(self):
        result = run_transform(
            assessments=[assessment(weight=-1)],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "2026-10" / result.run_id
            files = save_transformation_result(result, output_dir)

            self.assertEqual(
                set(files),
                {
                    "dim_child",
                    "fact_assessment",
                    "fact_supplement",
                    "fact_health_trends",
                    "quarantine_records",
                    "profiles",
                    "validations",
                    "run_summary",
                },
            )
            for output_file in files.values():
                self.assertTrue(output_file.is_file())

            with files["fact_assessment"].open(
                encoding="utf-8-sig", newline=""
            ) as csv_file:
                reader = csv.DictReader(csv_file)
                self.assertIn("assessment_id", reader.fieldnames)
                self.assertEqual(list(reader), [])

            with files["quarantine_records"].open(
                encoding="utf-8-sig", newline=""
            ) as csv_file:
                quarantine_row = next(csv.DictReader(csv_file))
            source_record = json.loads(quarantine_row["source_record"])
            self.assertEqual(source_record["id"], "assessment-1")

            with files["run_summary"].open(
                encoding="utf-8-sig", newline=""
            ) as csv_file:
                summary = next(csv.DictReader(csv_file))
            self.assertEqual(summary["status"], "MANUAL_REVIEW")
            self.assertEqual(
                json.loads(summary["metrics"])["tbl_assessments"]["records_read"],
                1,
            )

    def test_legacy_chart_only_helper_still_works(self):
        rows = transform_health_trends(
            [assessment()],
            [{"id": "child-1", "barangay": "Barangay 1"}],
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["assessment_month_year"], "2026-10")


if __name__ == "__main__":
    unittest.main()
