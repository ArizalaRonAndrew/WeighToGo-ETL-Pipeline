import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from pipelines.extractions.extractor import WeighToGoExtractor


class TestWeighToGoExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = WeighToGoExtractor(
            supabase_url="https://project.supabase.co",
            api_key="test-key",
        )

    @patch("pipelines.extractions.extractor.requests.get")
    def test_extracts_monthly_assessments(self, mock_get):
        response = MagicMock()
        response.json.return_value = [{"id": "assessment-1"}]
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        result = self.extractor.extract_batch("assessment", "October 2026")

        self.assertEqual(result, [{"id": "assessment-1"}])
        mock_get.assert_called_once_with(
            "https://project.supabase.co/rest/v1/tbl_assessments",
            headers={
                "apikey": "test-key",
                "Authorization": "Bearer test-key",
            },
            params=[
                (
                    "select",
                    "id,child_id,date_measured,weight,height,age_in_months,"
                    "wfa_status,hfa_status,wfl_h_status,status,created_at",
                ),
                ("date_measured", "gte.2026-10-01"),
                ("date_measured", "lt.2026-11-01"),
                ("order", "id.asc"),
                ("limit", "1000"),
                ("offset", "0"),
            ],
            timeout=30,
        )

    @patch("pipelines.extractions.extractor.requests.get")
    def test_extracts_children_referenced_in_monthly_records(self, mock_get):
        assessment_response = MagicMock()
        assessment_response.json.return_value = [{"child_id": "child-1"}]
        assessment_response.raise_for_status.return_value = None
        supplements_response = MagicMock()
        supplements_response.json.return_value = [{"child_id": "child-2"}]
        supplements_response.raise_for_status.return_value = None
        children_response = MagicMock()
        children_response.json.return_value = [{"id": "child-1"}, {"id": "child-2"}]
        children_response.raise_for_status.return_value = None
        mock_get.side_effect = [
            assessment_response,
            supplements_response,
            children_response,
        ]

        result = self.extractor.extract_batch("children", "2026-10")

        self.assertEqual(result, [{"id": "child-1"}, {"id": "child-2"}])
        self.assertEqual(mock_get.call_count, 3)
        self.assertIn(
            "/tbl_assessments",
            mock_get.call_args_list[0].args[0],
        )
        self.assertIn(
            "/tbl_supplements",
            mock_get.call_args_list[1].args[0],
        )
        self.assertIn(
            "/tbl_children",
            mock_get.call_args_list[2].args[0],
        )
        child_columns = mock_get.call_args_list[2].kwargs["params"][0][1]
        self.assertNotIn("name", child_columns.split(","))
        self.assertNotIn("parent_contact", child_columns.split(","))
        self.assertEqual(
            mock_get.call_args_list[2].kwargs["params"][1],
            ("id", "in.(child-1,child-2)"),
        )

    @patch("pipelines.extractions.extractor.requests.get")
    def test_connection_checks_actual_children_table(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        self.assertTrue(self.extractor.connect())
        self.assertIn("/tbl_children", mock_get.call_args.args[0])

    @patch("pipelines.extractions.extractor.requests.get")
    def test_paginates_full_results(self, mock_get):
        first_page = MagicMock()
        first_page.json.return_value = [{"id": "1"}, {"id": "2"}]
        first_page.raise_for_status.return_value = None
        second_page = MagicMock()
        second_page.json.return_value = [{"id": "3"}]
        second_page.raise_for_status.return_value = None
        mock_get.side_effect = [first_page, second_page]

        with patch("pipelines.extractions.extractor._PAGE_SIZE", 2):
            result = self.extractor._fetch_rows("tbl_children", [])

        self.assertEqual(result, [{"id": "1"}, {"id": "2"}, {"id": "3"}])
        self.assertEqual(mock_get.call_args_list[0].kwargs["params"][-1], ("offset", "0"))
        self.assertEqual(mock_get.call_args_list[1].kwargs["params"][-1], ("offset", "2"))

    @patch("pipelines.extractions.extractor.requests.get")
    def test_connection_failure_is_reported(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("offline")

        self.assertFalse(self.extractor.connect())

    def test_rejects_unknown_table_and_invalid_period(self):
        with self.assertRaises(ValueError):
            self.extractor.extract_batch("unknown", "October 2026")
        with self.assertRaises(ValueError):
            self.extractor.extract_batch("assessment", "October")

    def test_saves_extracted_rows_to_csv_with_contract_columns(self):
        data = [{
            "id": "assessment-1",
            "child_id": "child-1",
            "date_measured": "2026-10-12",
            "weight": 12.5,
            "height": 90,
            "age_in_months": 24,
            "wfa_status": "NORMAL",
            "hfa_status": "NORMAL",
            "wfl_h_status": "NORMAL",
            "status": "active",
            "created_at": "2026-10-12T10:00:00+00:00",
        }]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "assessment.csv"

            self.extractor.save_batch_csv(data, "assessment", str(output_path))

            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                self.assertEqual(
                    reader.fieldnames,
                    [
                        "id", "child_id", "date_measured", "weight", "height",
                        "age_in_months", "wfa_status", "hfa_status",
                        "wfl_h_status", "status", "created_at",
                    ],
                )
                self.assertEqual(next(reader)["id"], "assessment-1")

    def test_saves_csv_headers_when_extraction_is_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "assessment.csv"

            self.extractor.save_batch_csv([], "assessment", str(output_path))

            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.reader(csv_file)
                self.assertEqual(next(reader)[0], "id")
                self.assertEqual(list(reader), [])


if __name__ == "__main__":
    unittest.main()
