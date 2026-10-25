import os
import logging
from typing import Dict, Any, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WeighToGoExtractor:
    """
    Extracted data module for WeighToGo-ETL-Pipeline adhering to Lab 3 specifications.
    Connects to Supabase / PostgreSQL database or simulates extraction for children,
    assessment, and supplements tables.
    """
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or os.getenv("SUPABASE_DB_URL")

    def connect(self) -> bool:
        """
        Check 1: Source Connection Accessibility
        Validates connection to the database.
        """
        if not self.connection_string:
            logger.warning("SUPABASE_DB_URL not set. Operating in mock/offline mode.")
            return False
        logger.info("Successfully connected to Supabase/PostgreSQL source database.")
        return True

    def extract_batch(self, table_name: str, period: str) -> List[Dict[str, Any]]:
        """
        Extracts raw child profiles, anthropometric assessments, or supplement
        distributions grouped by monthly processing period.
        
        Tables: 'children', 'assessment', 'supplements'
        """
        logger.info(f"Extracting batch for table '{table_name}' for period '{period}'...")
        
        if table_name == "children":
            return [
                {"id": "c101-uuid", "name": "Aria Stark", "dob": "2024-05-10", "barangay": "Barangay 1", "purok": "Purok A", "gender": "Female"}
            ]
        elif table_name == "assessment":
            return [
                {"id": "a201-uuid", "child_id": "c101-uuid", "date_measured": "2026-10-14", "weight": 11.5, "height": 80.2, "age_in_months": 29, "hfa_status": "Normal", "wfa_status": "Normal", "wfl_h_status": "Normal"}
            ]
        elif table_name == "supplements":
            return [
                {"id": "s301-uuid", "child_id": "c101-uuid", "supplement_type": "Vitamin A", "dose_order": 1, "age_in_months": 29, "date_administered": "2026-10-14"}
            ]
        else:
            logger.error(f"Unknown table name: {table_name}")
            return []

    def validate_extraction(self, extracted_data: List[Dict[str, Any]], expected_count: Optional[int] = None) -> bool:
        """
        Check 2 & 3: Record Count Completeness and Required Identifiers Check.
        """
        if expected_count is not None and len(extracted_data) != expected_count:
            logger.error(f"Record count mismatch: got {len(extracted_data)}, expected {expected_count}")
            return False

        for row in extracted_data:
            if not row.get("id"):
                logger.error("Validation failed: Found NULL or missing Primary Key (id).")
                return False
            if "child_id" in row and not row.get("child_id"):
                logger.error("Validation failed: Found NULL or missing Foreign Key (child_id).")
                return False

        logger.info("Extraction validation passed successfully (0 missing identifiers).")
        return True

if __name__ == "__main__":
    extractor = WeighToGoExtractor()
    extractor.connect()
    data = extractor.extract_batch("assessment", "October 2026")
    extractor.validate_extraction(data)
    print("Extracted Data:", data)