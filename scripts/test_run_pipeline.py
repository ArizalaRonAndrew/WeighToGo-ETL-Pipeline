import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from pipelines.extractions.extractor import WeighToGoExtractor
from scripts.run_demo import load_inputs
from scripts.run_pipeline import run_pipeline


class TestRunPipeline(unittest.TestCase):
    def test_extracted_rows_are_passed_to_transformation_and_saved(self):
        inputs = load_inputs()
        extractor = MagicMock()
        extractor.connect.return_value = True
        extractor.extract_batch.side_effect = [
            inputs["assessments"],
            inputs["supplements"],
            inputs["children"],
        ]
        extractor.validate_extraction.return_value = True
        csv_writer = WeighToGoExtractor(
            supabase_url="https://project.supabase.co",
            api_key="test-key",
        )
        extractor.save_batch_csv.side_effect = csv_writer.save_batch_csv

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_pipeline(
                "2026-10",
                output_root=Path(temp_dir),
                extractor=extractor,
            )

            self.assertEqual(result.status, "APPROVED")
            self.assertEqual(len(result.fact_assessment), 4)
            self.assertEqual(len(result.fact_supplement), 3)
            self.assertEqual(
                [call.args[0] for call in extractor.extract_batch.call_args_list],
                ["assessment", "supplements", "children"],
            )
            self.assertTrue(
                (Path(temp_dir) / "extracted" / "2026-10"
                 / "assessment_2026-10.csv").is_file()
            )
            self.assertTrue(
                (Path(temp_dir) / "transformed" / "2026-10"
                 / result.run_id / "run_summary.csv").is_file()
            )

    def test_failed_connection_stops_before_extraction(self):
        extractor = MagicMock()
        extractor.connect.return_value = False

        with self.assertRaisesRegex(RuntimeError, "Could not connect"):
            run_pipeline("2026-10", extractor=extractor)
        extractor.extract_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
