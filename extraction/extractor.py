import os
import requests
import json
import logging
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ExtractionService:
    """
    Extraction service for the WeighToGo ETL pipeline.
    Handles fetching raw data from designated APIs or source files.
    """
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv("SOURCE_API_URL", "https://api.example.com/v1")

    def extract_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Extracts raw data from a given API endpoint.
        
        Args:
            endpoint (str): The specific API endpoint or resource path.
            params (dict, optional): Query parameters for the request.
            
        Returns:
            dict or list: The extracted JSON data, or None if extraction failed.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.info(f"Extracting data from {url}")
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logger.info("Successfully extracted data.")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error during data extraction: {e}")
            return None

    def save_raw_data(self, data: Any, output_filepath: str) -> bool:
        """
        Saves extracted raw data to a local JSON file.
        """
        try:
            os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.info(f"Raw data successfully saved to {output_filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save raw data: {e}")
            return False

if __name__ == "__main__":
    # Example usage
    service = ExtractionService()
    print("ExtractionService initialized successfully.")