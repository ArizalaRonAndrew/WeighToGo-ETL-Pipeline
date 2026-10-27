import unittest
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
                ("select", "*"),
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
            result = self.extractor._fetch_rows("children", [])

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


if __name__ == "__main__":
    unittest.main()
