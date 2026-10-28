import csv
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000
_CHILD_ID_BATCH_SIZE = 100
_SOURCE_TABLES = {
    "children": ("tbl_children", None),
    "assessment": ("tbl_assessments", "date_measured"),
    "supplements": ("tbl_supplements", "date_administered"),
}
_SOURCE_COLUMNS = {
    "tbl_children": (
        "id,dob,barangay,purok,gender,is_ip,status,created_at"
    ),
    "tbl_assessments": (
        "id,child_id,date_measured,weight,height,age_in_months,"
        "wfa_status,hfa_status,wfl_h_status,status,created_at"
    ),
    "tbl_supplements": (
        "id,child_id,supplement_type,dose_order,age_in_months,"
        "date_administered,status,created_at"
    ),
}


def _load_project_env() -> None:
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.is_file():
        return

    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if name and value:
            os.environ.setdefault(name, value)


def _month_bounds(period: str) -> tuple[date, date]:
    for date_format in ("%B %Y", "%Y-%m"):
        try:
            month = datetime.strptime(period, date_format).date().replace(day=1)
            break
        except ValueError:
            continue
    else:
        raise ValueError("period must be formatted as 'Month YYYY' or 'YYYY-MM'")

    if month.month == 12:
        next_month = date(month.year + 1, 1, 1)
    else:
        next_month = date(month.year, month.month + 1, 1)
    return month, next_month


class WeighToGoExtractor:
    """Extract monthly child health records from Supabase via its REST API."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30,
    ):
        _load_project_env()
        self.supabase_url = (
            supabase_url or os.getenv("SUPABASE_URL")
        )
        self.api_key = api_key or os.getenv("SUPABASE_ANON_KEY")
        self.timeout = timeout

    @property
    def rest_url(self) -> str:
        if not self.supabase_url or not self.api_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be configured "
                "in the environment or project .env file"
            )
        return f"{self.supabase_url.rstrip('/')}/rest/v1"

    @property
    def headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError(
                "SUPABASE_ANON_KEY must be configured in the environment "
                "or project .env file"
            )
        return {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }

    def connect(self) -> bool:
        """Check that the configured key can read the source tables."""
        try:
            requests.get(
                f"{self.rest_url}/{_SOURCE_TABLES['children'][0]}",
                headers=self.headers,
                params={"select": "id", "limit": 1},
                timeout=self.timeout,
            ).raise_for_status()
        except RuntimeError as error:
            logger.error("Supabase configuration is incomplete: %s", error)
            return False
        except requests.exceptions.RequestException as error:
            logger.error("Supabase connection check failed: %s", error)
            return False

        logger.info("Successfully connected to the Supabase REST API.")
        return True

    def _fetch_rows(
        self,
        table_name: str,
        filters: List[Tuple[str, str]],
        select: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        selected_columns = select or _SOURCE_COLUMNS.get(table_name)
        if selected_columns is None:
            raise ValueError(f"No extraction column contract for {table_name}")
        rows: List[Dict[str, Any]] = []
        offset = 0

        while True:
            params = [
                ("select", selected_columns),
                *filters,
                ("order", "id.asc"),
                ("limit", str(_PAGE_SIZE)),
                ("offset", str(offset)),
            ]
            response = requests.get(
                f"{self.rest_url}/{table_name}",
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list) or not all(
                isinstance(row, dict) for row in page
            ):
                raise ValueError(
                    f"Supabase returned an invalid response for {table_name}"
                )

            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                return rows
            offset += _PAGE_SIZE

    def extract_batch(
        self,
        table_name: str,
        period: str,
    ) -> List[Dict[str, Any]]:
        """Extract records for a month from the configured Supabase project."""
        if table_name not in _SOURCE_TABLES:
            raise ValueError(
                f"Unknown table {table_name!r}; expected one of "
                f"{', '.join(_SOURCE_TABLES)}"
            )

        month_start, next_month = _month_bounds(period)
        source_table, date_column = _SOURCE_TABLES[table_name]
        if date_column is not None:
            return self._fetch_rows(
                source_table,
                [
                    (date_column, f"gte.{month_start.isoformat()}"),
                    (date_column, f"lt.{next_month.isoformat()}"),
                ],
                select=_SOURCE_COLUMNS[source_table],
            )

        child_ids = {
            row["child_id"]
            for source_table, source_date_column in (
                ("tbl_assessments", "date_measured"),
                ("tbl_supplements", "date_administered"),
            )
            for row in self._fetch_rows(
                source_table,
                [
                    (source_date_column, f"gte.{month_start.isoformat()}"),
                    (source_date_column, f"lt.{next_month.isoformat()}"),
                ],
                select="child_id",
            )
            if row.get("child_id")
        }
        children: List[Dict[str, Any]] = []
        sorted_ids = sorted(child_ids)
        for start in range(0, len(sorted_ids), _CHILD_ID_BATCH_SIZE):
            batch = sorted_ids[start:start + _CHILD_ID_BATCH_SIZE]
            children.extend(
                self._fetch_rows(
                    "tbl_children",
                    [("id", f"in.({','.join(batch)})")],
                    select=_SOURCE_COLUMNS["tbl_children"],
                )
            )
        return children

    def save_batch_csv(
        self,
        extracted_data: List[Dict[str, Any]],
        table_name: str,
        output_filepath: str,
    ) -> None:
        """Save extracted rows as CSV using the source table's column order."""
        if table_name not in _SOURCE_TABLES:
            raise ValueError(
                f"Unknown table {table_name!r}; expected one of "
                f"{', '.join(_SOURCE_TABLES)}"
            )

        source_table = _SOURCE_TABLES[table_name][0]
        fieldnames = _SOURCE_COLUMNS[source_table].split(",")
        output_path = Path(output_filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(extracted_data)
        logger.info("Saved %s extracted rows to %s", len(extracted_data), output_path)

    def validate_extraction(
        self,
        extracted_data: List[Dict[str, Any]],
        expected_count: Optional[int] = None,
    ) -> bool:
        """Check record counts and required identifiers."""
        if expected_count is not None and len(extracted_data) != expected_count:
            logger.error(
                "Record count mismatch: got %s, expected %s",
                len(extracted_data),
                expected_count,
            )
            return False

        for row in extracted_data:
            if not row.get("id"):
                logger.error("Validation failed: missing Primary Key (id).")
                return False
            if "child_id" in row and not row.get("child_id"):
                logger.error("Validation failed: missing Foreign Key (child_id).")
                return False

        logger.info("Extraction validation passed successfully.")
        return True


if __name__ == "__main__":
    extractor = WeighToGoExtractor()
    if not extractor.connect():
        raise SystemExit("Unable to connect to the configured Supabase project.")
    table_name = "assessment"
    period = "October 2026"
    data = extractor.extract_batch(table_name, period)
    if not extractor.validate_extraction(data):
        raise SystemExit("Extraction validation failed; CSV was not written.")
    month_start, _ = _month_bounds(period)
    output_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "extracted"
        / f"{table_name}_{month_start:%Y-%m}.csv"
    )
    extractor.save_batch_csv(data, table_name, str(output_path))
    print(f"Extracted {len(data)} {table_name} records to {output_path}.")
