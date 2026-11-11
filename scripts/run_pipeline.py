"""Extract a monthly Supabase batch and transform it into local CSV outputs."""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from pipelines.extractions.extractor import WeighToGoExtractor
from pipelines.transformation.health_trends import (
    TransformationResult,
    save_transformation_result,
    transform_batch,
)


ROOT = Path(__file__).resolve().parents[1]


def month_window(period: str) -> Tuple[date, date]:
    try:
        month_start = datetime.strptime(period, "%Y-%m").date().replace(day=1)
    except ValueError as error:
        raise ValueError("period must be formatted as YYYY-MM") from error

    if month_start.month == 12:
        month_end = date(month_start.year + 1, 1, 1)
    else:
        month_end = date(month_start.year, month_start.month + 1, 1)
    return month_start, month_end


def run_pipeline(
    period: str,
    output_root: Optional[Path] = None,
    extractor: Optional[WeighToGoExtractor] = None,
) -> TransformationResult:
    """Fetch all source tables, validate them, transform, and save CSV reports."""
    batch_start, batch_end = month_window(period)
    base_output = output_root or ROOT / "data"
    source_output = base_output / "extracted" / period
    transformer_output = base_output / "transformed" / period
    service = extractor or WeighToGoExtractor()

    if not service.connect():
        raise RuntimeError(
            "Could not connect to Supabase. Check SUPABASE_URL, "
            "SUPABASE_ANON_KEY, network access, and table permissions."
        )

    extracted: Dict[str, List[dict]] = {}
    for table_name in ("assessment", "supplements", "children"):
        rows = service.extract_batch(table_name, period)
        if not service.validate_extraction(rows):
            raise RuntimeError(
                f"Extraction validation failed for {table_name}; "
                "transformation was not started."
            )
        extracted[table_name] = rows
        print(f"Extracted {len(rows)} {table_name} records for {period}.")

    extraction_run_id = f"EXT_{uuid4()}"
    source_output.mkdir(parents=True, exist_ok=True)
    for table_name, rows in extracted.items():
        output_path = source_output / f"{table_name}_{period}.csv"
        service.save_batch_csv(rows, table_name, str(output_path))
        print(f"Saved source CSV: {output_path}")

    result = transform_batch(
        extracted["assessment"],
        extracted["children"],
        extracted["supplements"],
        parent_extraction_run_id=extraction_run_id,
        batch_start=batch_start.isoformat(),
        batch_end=batch_end.isoformat(),
    )
    saved = save_transformation_result(
        result,
        transformer_output / result.run_id,
    )

    total_read = sum(
        item["records_read"] for item in result.metrics.values()
    )
    total_output = sum(
        item["records_output"] for item in result.metrics.values()
    )
    total_rejected = sum(
        item["records_rejected"] for item in result.metrics.values()
    )
    print(
        f"Transformation status: {result.status}; "
        f"read={total_read}, output={total_output}, rejected={total_rejected}"
    )
    print(f"Transformation reports: {saved['run_summary'].parent}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract children, assessment, and supplement records from "
            "Supabase, then transform the monthly batch."
        )
    )
    parser.add_argument(
        "--period",
        required=True,
        help="Monthly batch in YYYY-MM format, for example 2026-10",
    )
    args = parser.parse_args()

    try:
        result = run_pipeline(args.period)
    except (RuntimeError, ValueError) as error:
        print(f"Pipeline failed: {error}", file=sys.stderr)
        return 1

    if result.status != "APPROVED":
        print(
            "Batch was extracted and transformed, but it is not approved; "
            "review validations and quarantine before presenting it as accepted.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
