import unittest
from unittest.mock import patch, MagicMock
import requests
from extraction.extractor import ExtractionService

class TestExtractionService(unittest.TestCase):
    def setUp(self):
        self.service = ExtractionService(base_url="https://api.test.com")

    @patch('extraction.extractor.requests.get')
    def test_extract_data_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "data": [1, 2, 3]}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.service.extract_data("weights")
        self.assertEqual(result, {"status": "success", "data": [1, 2, 3]})
        mock_get.assert_called_once_with("https://api.test.com/weights", params=None, timeout=30)

    @patch('extraction.extractor.requests.get')
    def test_extract_data_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        result = self.service.extract_data("weights")
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
