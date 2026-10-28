import csv
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

logger = logging.getLogger(__name__)

INDICATORS = (
    ("WFA", "wfa_status"),
    ("HFA", "hfa_status"),
    ("WFL", "wfl_h_status"),
)
_GENDER_MAP = {
    "M": "MALE",
    "MALE": "MALE",
    "BOY": "MALE",
    "F": "FEMALE",
    "FEMALE": "FEMALE",
    "GIRL": "FEMALE",
}
_REQUIRED = {
    "tbl_children": ("id", "dob", "barangay", "purok", "gender", "status"),
    "tbl_assessments": (
        "id", "child_id", "date_measured", "weight", "height",
        "age_in_months", "status",
    ),
    "tbl_supplements": (
        "id", "child_id", "supplement_type", "dose_order",
        "age_in_months", "date_administered", "status",
    ),
}


@dataclass
class TransformationResult:
    """In-memory transformed batch and audit details."""

    run_id: str
    batch_id: str
    parent_extraction_run_id: str
    batch_start: str
    batch_end: str
    started_at_utc: str
    ended_at_utc: Optional[str] = None
    dim_child: List[Dict[str, Any]] = field(default_factory=list)
    fact_assessment: List[Dict[str, Any]] = field(default_factory=list)
    fact_supplement: List[Dict[str, Any]] = field(default_factory=list)
    fact_health_trends: List[Dict[str, Any]] = field(default_factory=list)
    quarantine_records: List[Dict[str, Any]] = field(default_factory=list)
    profiles: List[Dict[str, Any]] = field(default_factory=list)
    validations: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Dict[str, int]] = field(default_factory=dict)
    rules_applied: Dict[str, int] = field(default_factory=dict)
    status: str = "FAILED"


_TRANSFORMATION_CSV_FIELDS = {
    "dim_child": (
        "batch_id", "run_id", "child_key", "source_child_id", "date_of_birth",
        "barangay_name", "purok_name", "gender", "is_ip", "source_status",
    ),
    "fact_assessment": (
        "batch_id", "run_id", "assessment_id", "child_key", "date_measured",
        "assessment_month", "age_months", "weight_kg", "height_cm",
        "wfa_status", "hfa_status", "wfl_h_status",
    ),
    "fact_supplement": (
        "batch_id", "run_id", "supplement_id", "child_key", "date_administered",
        "supplement_month", "supplement_type", "dose_order", "age_months",
    ),
    "fact_health_trends": (
        "batch_id", "run_id", "barangay_name", "assessment_month", "indicator",
        "nutritional_status", "total_count",
    ),
    "quarantine_records": (
        "batch_id", "run_id", "parent_extraction_run_id", "table_name",
        "source_record_id", "rule_id", "reason", "source_record",
        "rejected_at_utc",
    ),
    "profiles": (
        "batch_id", "run_id", "table_name", "column_name", "issue_type",
        "sample_values", "affected_records", "input_records",
        "affected_percentage", "planned_treatment", "rule_id",
    ),
    "validations": (
        "check_name", "severity", "table_name", "passed", "message",
        "record_id",
    ),
}


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _write_csv(
    output_path: Path,
    rows: List[Dict[str, Any]],
    default_fields: Tuple[str, ...],
) -> None:
    fieldnames = list(default_fields)
    for row in rows:
        for field_name in row:
            if field_name not in fieldnames:
                fieldnames.append(field_name)

    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {
                key: _csv_value(value)
                for key, value in row.items()
            }
            for row in rows
        )


def save_transformation_result(
    result: TransformationResult,
    output_directory: Union[str, Path],
) -> Dict[str, Path]:
    """Persist transformation outputs and audit details as separate CSV files."""
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    datasets = {
        "dim_child": result.dim_child,
        "fact_assessment": result.fact_assessment,
        "fact_supplement": result.fact_supplement,
        "fact_health_trends": result.fact_health_trends,
        "quarantine_records": result.quarantine_records,
        "profiles": result.profiles,
        "validations": result.validations,
    }
    files: Dict[str, Path] = {}
    for dataset_name, rows in datasets.items():
        file_path = output_path / f"{dataset_name}.csv"
        _write_csv(
            file_path,
            rows,
            _TRANSFORMATION_CSV_FIELDS[dataset_name],
        )
        files[dataset_name] = file_path

    summary_path = output_path / "run_summary.csv"
    summary_rows = [{
        "run_id": result.run_id,
        "batch_id": result.batch_id,
        "parent_extraction_run_id": result.parent_extraction_run_id,
        "batch_start": result.batch_start,
        "batch_end_exclusive": result.batch_end,
        "started_at_utc": result.started_at_utc,
        "ended_at_utc": result.ended_at_utc,
        "status": result.status,
        "metrics": result.metrics,
        "rules_applied": result.rules_applied,
    }]
    _write_csv(
        summary_path,
        summary_rows,
        (
            "run_id", "batch_id", "parent_extraction_run_id", "batch_start",
            "batch_end_exclusive", "started_at_utc", "ended_at_utc", "status",
            "metrics", "rules_applied",
        ),
    )
    files["run_summary"] = summary_path
    return files


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return date.fromisoformat(text)
        except ValueError:
            try:
                return datetime.fromisoformat(
                    text.replace("Z", "+00:00")
                ).date()
            except ValueError as error:
                raise ValueError("not a valid ISO date") from error
    raise ValueError("not a valid ISO date")


def _month(value: date) -> str:
    return value.strftime("%Y-%m")


def _age_in_months(birth_date: date, measured_date: date) -> int:
    if measured_date < birth_date:
        raise ValueError("measurement date precedes date of birth")
    months = (measured_date.year - birth_date.year) * 12
    months += measured_date.month - birth_date.month
    if measured_date.day < birth_date.day:
        months -= 1
    return months


def _timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rule_reject(
    result: TransformationResult,
    table_name: str,
    record: Mapping[str, Any],
    rule_id: str,
    reason: str,
) -> None:
    result.rules_applied[rule_id] = result.rules_applied.get(rule_id, 0) + 1
    record_id = record.get("id")
    result.quarantine_records.append({
        "batch_id": result.batch_id,
        "run_id": result.run_id,
        "parent_extraction_run_id": result.parent_extraction_run_id,
        "table_name": table_name,
        "source_record_id": str(record_id) if record_id is not None else None,
        "rule_id": rule_id,
        "reason": reason,
        "source_record": {
            key: value
            for key, value in record.items()
            if key.lower() not in {
                "password", "name", "parent_contact", "parent_name", "email",
            }
        },
        "rejected_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    logger.warning(
        "Transformation rejected a %s record; batch=%s rule=%s reason=%s",
        table_name,
        result.run_id,
        rule_id,
        reason,
    )


def _profile_issue(
    result: TransformationResult,
    table_name: str,
    column_name: str,
    issue_type: str,
    affected_ids: Iterable[Any],
    source_rows: List[Mapping[str, Any]],
    planned_treatment: str,
    rule_id: str,
) -> None:
    affected = list(affected_ids)
    if not affected:
        return
    rows_by_id = {str(row.get("id")): row for row in source_rows}
    examples = []
    for record_id in sorted(set(affected), key=str)[:3]:
        row = rows_by_id.get(str(record_id), {})
        value = row.get(column_name)
        sample = "NULL" if value is None else value
        if sample not in examples:
            examples.append(sample)
    result.profiles.append({
        "batch_id": result.batch_id,
        "run_id": result.run_id,
        "table_name": table_name,
        "column_name": column_name,
        "issue_type": issue_type,
        "sample_values": examples,
        "affected_records": len(affected),
        "input_records": len(source_rows),
        "affected_percentage": round(
            100 * len(affected) / len(source_rows), 2
        ) if source_rows else 0.0,
        "planned_treatment": planned_treatment,
        "rule_id": rule_id,
    })


def _deduplicate(
    rows: List[Mapping[str, Any]],
    table_name: str,
    result: TransformationResult,
) -> List[Mapping[str, Any]]:
    grouped: Dict[Any, List[Mapping[str, Any]]] = defaultdict(list)
    missing_ids = []
    for row in rows:
        record_id = row.get("id")
        if record_id in (None, ""):
            missing_ids.append(row)
        else:
            grouped[record_id].append(row)

    for row in missing_ids:
        _rule_reject(result, table_name, row, "C-05", "missing primary key")

    duplicate_ids = [
        record_id
        for record_id, group in grouped.items()
        if len(group) > 1
        for _ in group
    ]
    _profile_issue(
        result,
        table_name,
        "id",
        "duplicate primary key",
        duplicate_ids,
        rows,
        "Keep the unique row with the newest created_at; quarantine older rows. "
        "Quarantine all tied or undated duplicates because recency is ambiguous.",
        "C-04",
    )

    selected = []
    for record_id, group in grouped.items():
        if len(group) == 1:
            selected.append(group[0])
            continue
        dated = [(index, row, _timestamp(row.get("created_at")))
                 for index, row in enumerate(group)]
        if any(stamp is None for _, _, stamp in dated):
            for row in group:
                _rule_reject(
                    result, table_name, row, "C-04",
                    "duplicate id cannot be resolved: created_at missing or invalid",
                )
            continue
        newest = max(stamp for _, _, stamp in dated if stamp is not None)
        latest = [row for _, row, stamp in dated if stamp == newest]
        if len(latest) != 1:
            for row in group:
                _rule_reject(
                    result, table_name, row, "C-04",
                    "duplicate id has tied latest created_at values",
                )
            continue
        selected.append(latest[0])
        for row in group:
            if row is not latest[0]:
                _rule_reject(
                    result, table_name, row, "C-04",
                    "superseded duplicate; a newer created_at row was retained",
                )
    return selected


def _required_columns(
    rows: List[Mapping[str, Any]],
    table_name: str,
    result: TransformationResult,
) -> None:
    for row in rows:
        missing = [column for column in _REQUIRED[table_name] if column not in row]
        if missing:
            _rule_reject(
                result, table_name, row, "S-05",
                "missing required columns: " + ", ".join(missing),
            )


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).upper()


def _record_rule(result: TransformationResult, rule_id: str) -> None:
    result.rules_applied[rule_id] = result.rules_applied.get(rule_id, 0) + 1


def _status_active(
    row: Mapping[str, Any],
    table_name: str,
    result: TransformationResult,
) -> bool:
    status = row.get("status")
    normalized = str(status).strip().upper() if status is not None else ""
    if normalized == "ACTIVE":
        return True
    _rule_reject(
        result,
        table_name,
        row,
        "B-03",
        f"source status is {normalized or 'NULL'}; only ACTIVE rows are transformed",
    )
    return False


def _positive_measurement(value: Any, column: str) -> Decimal:
    try:
        measurement = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{column} is not numeric") from None
    if not measurement.is_finite() or measurement <= 0:
        raise ValueError(f"{column} must be a positive finite number")
    if measurement > Decimal("999.99"):
        raise ValueError(f"{column} exceeds DECIMAL(5,2)")
    return measurement.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _standard_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "1", "yes"}:
            return True
        if normalized in {"false", "f", "0", "no", ""}:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError("is_ip must be a boolean")


def _is_valid_bool(value: Any) -> bool:
    try:
        _standard_bool(value)
    except ValueError:
        return False
    return True


def _integer_value(value: Any, column: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{column} must be an integer")
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{column} must be an integer") from None
    try:
        if Decimal(str(value)) != Decimal(converted):
            raise ValueError(f"{column} must be an integer")
    except InvalidOperation:
        raise ValueError(f"{column} must be an integer") from None
    return converted


def _is_valid_integer(value: Any, column: str) -> bool:
    try:
        _integer_value(value, column)
    except ValueError:
        return False
    return True


def transform_batch(
    assessments: Iterable[Mapping[str, Any]],
    children: Iterable[Mapping[str, Any]],
    supplements: Iterable[Mapping[str, Any]],
    *,
    parent_extraction_run_id: str,
    batch_start: str,
    batch_end: str,
    run_id: Optional[str] = None,
    as_of_date: Optional[date] = None,
) -> TransformationResult:
    """Profile, clean, standardize, validate, and transform one extraction batch.

    ``batch_end`` is exclusive. Results remain in memory; persistence is a
    separate transactional load step defined by the accompanying SQL contract.
    """
    start_date = _parse_date(batch_start)
    end_date = _parse_date(batch_end)
    if start_date >= end_date:
        raise ValueError("batch_start must be before exclusive batch_end")
    if not parent_extraction_run_id:
        raise ValueError("parent_extraction_run_id is required")
    batch_id = str(uuid5(
        NAMESPACE_URL,
        f"weigh-to-go:{parent_extraction_run_id}:{start_date}:{end_date}",
    ))
    result = TransformationResult(
        run_id=str(UUID(run_id)) if run_id else str(uuid4()),
        batch_id=batch_id,
        parent_extraction_run_id=parent_extraction_run_id,
        batch_start=start_date.isoformat(),
        batch_end=end_date.isoformat(),
        started_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    raw = {
        "tbl_children": list(children),
        "tbl_assessments": list(assessments),
        "tbl_supplements": list(supplements),
    }
    result.metrics = {
        table_name: {
            "records_read": len(rows),
            "records_output": 0,
            "records_rejected": 0,
        }
        for table_name, rows in raw.items()
    }

    for table_name, rows in raw.items():
        _required_columns(rows, table_name, result)
        expected_columns = set(_REQUIRED[table_name])
        for column in _REQUIRED[table_name]:
            missing_column_ids = [
                row.get("id") for row in rows if column not in row
            ]
            _profile_issue(
                result,
                table_name,
                column,
                "missing required column",
                missing_column_ids,
                rows,
                "Quarantine affected rows and fail the batch on source schema drift "
                "(S-05).",
                "S-05",
            )
        missing_columns = sorted({
            column
            for row in rows
            for column in expected_columns - set(row)
        })
        result.validations.append({
            "check_name": "required source columns",
            "severity": "CRITICAL",
            "table_name": table_name,
            "passed": not missing_columns,
            "message": (
                "all required columns are present"
                if not missing_columns
                else "missing columns: " + ", ".join(missing_columns)
            ),
        })

    for table_name, rows in raw.items():
        for column in _REQUIRED[table_name]:
            missing_value_ids = [
                row.get("id") for row in rows
                if column in row and row.get(column) is None
            ]
            _profile_issue(
                result,
                table_name,
                column,
                "null required value",
                missing_value_ids,
                rows,
                "Quarantine rows with missing required identifiers, dates, "
                "measurements, or fields (C-05/S-01).",
                "C-05",
            )

    for column in ("weight", "height"):
        invalid_measurement_ids = [
            row.get("id")
            for row in raw["tbl_assessments"]
            if _is_invalid_positive_measurement(row.get(column), column)
        ]
        _profile_issue(
            result,
            "tbl_assessments",
            column,
            "non-positive, non-numeric, or out-of-range measurement",
            invalid_measurement_ids,
            raw["tbl_assessments"],
            "Quarantine invalid anthropometric values (C-02).",
            "C-02",
        )
    for table_name, column in (
        ("tbl_assessments", "age_in_months"),
        ("tbl_supplements", "age_in_months"),
        ("tbl_supplements", "dose_order"),
    ):
        invalid_integer_ids = [
            row.get("id")
            for row in raw[table_name]
            if not _is_valid_integer(row.get(column), column)
        ]
        _profile_issue(
            result,
            table_name,
            column,
            "non-integer value",
            invalid_integer_ids,
            raw[table_name],
            "Quarantine failed integer conversions (S-03).",
            "S-03",
        )

    invalid_ip_ids = [
        row.get("id")
        for row in raw["tbl_children"]
        if not _is_valid_bool(row.get("is_ip"))
    ]
    _profile_issue(
        result,
        "tbl_children",
        "is_ip",
        "invalid boolean",
        invalid_ip_ids,
        raw["tbl_children"],
        "Quarantine values that cannot be converted to boolean (S-05).",
        "S-05",
    )

    today = as_of_date or date.today()
    future_supplement_ids = [
        row.get("id")
        for row in raw["tbl_supplements"]
        if _is_future_date(row.get("date_administered"), today)
    ]
    _profile_issue(
        result,
        "tbl_supplements",
        "date_administered",
        "future date",
        future_supplement_ids,
        raw["tbl_supplements"],
        "Quarantine future administration dates (C-03).",
        "C-03",
    )
    future_dob_ids = [
        row.get("id")
        for row in raw["tbl_children"]
        if _is_future_date(row.get("dob"), today)
    ]
    _profile_issue(
        result,
        "tbl_children",
        "dob",
        "future date of birth",
        future_dob_ids,
        raw["tbl_children"],
        "Quarantine future dates of birth (C-06).",
        "C-06",
    )

    # Rows missing contracted fields are quarantined before any field access.
    valid_rows = {
        table_name: [
            row for row in rows
            if all(column in row for column in _REQUIRED[table_name])
        ]
        for table_name, rows in raw.items()
    }
    deduped = {
        table_name: _deduplicate(rows, table_name, result)
        for table_name, rows in valid_rows.items()
    }
    active = {
        table_name: [
            row for row in rows
            if _status_active(row, table_name, result)
        ]
        for table_name, rows in deduped.items()
    }
    for table_name in raw:
        non_active_ids = [
            row.get("id") for row in deduped[table_name]
            if str(row.get("status") or "").strip().upper() != "ACTIVE"
        ]
        _profile_issue(
            result,
            table_name,
            "status",
            "non-active source record",
            non_active_ids,
            raw[table_name],
            "Quarantine all records not marked active (B-03).",
            "B-03",
        )

    whitespace_ids = [
        row.get("id") for row in active["tbl_children"]
        if isinstance(row.get("barangay"), str)
        and row["barangay"] != _normalized_text(row["barangay"])
    ]
    _profile_issue(
        result, "tbl_children", "barangay", "whitespace/casing inconsistency",
        whitespace_ids, raw["tbl_children"],
        "Trim, collapse internal whitespace, and uppercase (C-01, S-04).",
        "C-01",
    )
    purok_issue_ids = [
        row.get("id") for row in active["tbl_children"]
        if isinstance(row.get("purok"), str)
        and row["purok"] != _normalized_text(row["purok"])
    ]
    _profile_issue(
        result, "tbl_children", "purok", "whitespace/casing inconsistency",
        purok_issue_ids, raw["tbl_children"],
        "Trim, collapse spaces, and uppercase (S-04).",
        "S-04",
    )
    gender_issue_ids = [
        row.get("id") for row in active["tbl_children"]
        if str(row.get("gender", "")).strip().upper()
        not in {"MALE", "FEMALE"}
    ]
    _profile_issue(
        result, "tbl_children", "gender", "non-standard category",
        gender_issue_ids, raw["tbl_children"],
        "Map recognized aliases to MALE/FEMALE; set unrecognized values to "
        "UNKNOWN and record S-02.",
        "S-02",
    )
    invalid_date_profiles = (
        ("tbl_children", "dob", "S-01"),
        ("tbl_assessments", "date_measured", "S-01"),
        ("tbl_supplements", "date_administered", "S-01"),
    )
    for table_name, column, rule_id in invalid_date_profiles:
        invalid_ids = [
            row.get("id") for row in raw[table_name]
            if not _is_valid_date(row.get(column))
        ]
        _profile_issue(
            result,
            table_name,
            column,
            "invalid or unconvertible date",
            invalid_ids,
            raw[table_name],
            "Convert valid values to ISO 8601 DATE; quarantine conversion failures.",
            rule_id,
        )
    for column in ("wfa_status", "hfa_status", "wfl_h_status"):
        invalid_status_ids = [
            row.get("id")
            for row in raw["tbl_assessments"]
            if row.get(column) is not None
            and not isinstance(row.get(column), str)
        ]
        _profile_issue(
            result,
            "tbl_assessments",
            column,
            "non-text nutritional status",
            invalid_status_ids,
            raw["tbl_assessments"],
            "Quarantine records with non-text classifications (S-06).",
            "S-06",
        )
    invalid_supplement_ids = [
        row.get("id")
        for row in raw["tbl_supplements"]
        if str(row.get("supplement_type") or "").strip()
        not in {"Vitamin A", "Deworming"}
    ]
    _profile_issue(
        result,
        "tbl_supplements",
        "supplement_type",
        "unsupported category",
        invalid_supplement_ids,
        raw["tbl_supplements"],
        "Quarantine unsupported supplement categories (S-06).",
        "S-06",
    )

    children_by_id: Dict[Any, Dict[str, Any]] = {}
    for row in active["tbl_children"]:
        try:
            birth_date = _parse_date(row.get("dob"))
        except ValueError:
            _rule_reject(result, "tbl_children", row, "S-01", "invalid dob")
            continue
        if birth_date > today:
            _rule_reject(result, "tbl_children", row, "C-06", "dob is in the future")
            continue

        child_id = row["id"]
        barangay = _normalized_text(row.get("barangay", ""))
        purok = _normalized_text(row.get("purok", ""))
        if row.get("barangay") != barangay:
            _record_rule(result, "S-04")
        if row.get("purok") != purok:
            _record_rule(result, "S-04")
        if row.get("barangay") != str(row.get("barangay") or "").strip():
            _record_rule(result, "C-01")
        if not barangay:
            barangay = "UNSPECIFIED"
            _record_rule(result, "S-04")
        if not purok:
            purok = "UNSPECIFIED"
            _record_rule(result, "S-04")
        gender_value = str(row.get("gender", "")).strip().upper()
        gender = _GENDER_MAP.get(gender_value, "UNKNOWN")
        if gender_value != gender:
            _record_rule(result, "S-02")
        child_key = str(child_id)
        try:
            is_ip = _standard_bool(row.get("is_ip"))
        except ValueError as error:
            _rule_reject(result, "tbl_children", row, "S-05", str(error))
            continue
        child = {
            "batch_id": batch_id,
            "run_id": result.run_id,
            "child_key": child_key,
            "source_child_id": child_key,
            "date_of_birth": birth_date.isoformat(),
            "barangay_name": barangay,
            "purok_name": purok,
            "gender": gender,
            "is_ip": is_ip,
            "source_status": "ACTIVE",
        }
        children_by_id[child_id] = child
        result.dim_child.append(child)

    result.dim_child = list(children_by_id.values())
    valid_child_ids = set(children_by_id)
    for table_name in ("tbl_assessments", "tbl_supplements"):
        orphan_ids = [
            row.get("id") for row in active[table_name]
            if row.get("child_id") not in valid_child_ids
        ]
        _profile_issue(
            result,
            table_name,
            "child_id",
            "orphan, inactive, or invalid child reference",
            orphan_ids,
            raw[table_name],
            "Quarantine unresolved child references (B-01).",
            "B-01",
        )

    for row in active["tbl_assessments"]:
        non_text_status = next(
            (
                column for _, column in INDICATORS
                if row.get(column) is not None
                and not isinstance(row.get(column), str)
            ),
            None,
        )
        if non_text_status:
            _rule_reject(
                result, "tbl_assessments", row, "S-06",
                f"{non_text_status} must be text or null",
            )
            continue
        try:
            measured_date = _parse_date(row.get("date_measured"))
        except ValueError:
            _rule_reject(result, "tbl_assessments", row, "S-01", "invalid date_measured")
            continue
        if not start_date <= measured_date < end_date:
            _rule_reject(
                result, "tbl_assessments", row, "B-02",
                "date_measured is outside the extraction batch window",
            )
            continue
        child = children_by_id.get(row.get("child_id"))
        if child is None:
            _rule_reject(
                result, "tbl_assessments", row, "B-01",
                "orphan assessment: child is missing, inactive, or invalid",
            )
            continue
        try:
            age_months = _age_in_months(
                date.fromisoformat(child["date_of_birth"]),
                measured_date,
            )
            weight = _positive_measurement(row.get("weight"), "weight")
            height = _positive_measurement(row.get("height"), "height")
        except ValueError as error:
            message = str(error)
            if "must be a positive" in message:
                rule_id = "C-02"
            elif "weight" in message or "height" in message:
                rule_id = "S-03"
            else:
                rule_id = "B-05"
            _rule_reject(result, "tbl_assessments", row, rule_id, str(error))
            continue
        try:
            source_age = _integer_value(
                row.get("age_in_months"), "age_in_months"
            )
            if source_age < 0:
                raise ValueError
        except (TypeError, ValueError):
            _rule_reject(
                result,
                "tbl_assessments",
                row,
                "S-03",
                "age_in_months is missing or not a non-negative integer",
            )
            continue
        if source_age != age_months:
            _record_rule(result, "B-05")
        if weight != Decimal(str(row.get("weight"))):
            _record_rule(result, "S-03")
        if height != Decimal(str(row.get("height"))):
            _record_rule(result, "S-03")

        status_values = {
            "wfa_status": _standard_status(row.get("wfa_status")),
            "hfa_status": _standard_status(row.get("hfa_status")),
            "wfl_h_status": _standard_status(row.get("wfl_h_status")),
        }
        if any(
            status_values[column] != row.get(column)
            for column in status_values
        ):
            _record_rule(result, "S-06")
        fact = {
            "batch_id": batch_id,
            "run_id": result.run_id,
            "assessment_id": str(row["id"]),
            "child_key": child["child_key"],
            "date_measured": measured_date.isoformat(),
            "assessment_month": _month(measured_date),
            "age_months": age_months,
            "weight_kg": weight,
            "height_cm": height,
            **status_values,
        }
        if source_age is None or source_age != age_months:
            result.validations.append({
                "check_name": "source age consistency",
                "severity": "WARNING",
                "table_name": "tbl_assessments",
                "record_id": str(row["id"]),
                "message": (
                    "source age_in_months is missing/invalid or differs "
                    "from DOB-derived age"
                ),
            })
        result.fact_assessment.append(fact)

    for row in active["tbl_supplements"]:
        try:
            administered = _parse_date(row.get("date_administered"))
        except ValueError:
            _rule_reject(result, "tbl_supplements", row, "S-01", "invalid date_administered")
            continue
        if administered > today:
            _rule_reject(
                result, "tbl_supplements", row, "C-03",
                "date_administered is in the future",
            )
            continue
        if not start_date <= administered < end_date:
            _rule_reject(
                result, "tbl_supplements", row, "B-02",
                "date_administered is outside the extraction batch window",
            )
            continue
        child = children_by_id.get(row.get("child_id"))
        if child is None:
            _rule_reject(
                result, "tbl_supplements", row, "B-01",
                "orphan supplement: child is missing, inactive, or invalid",
            )
            continue
        try:
            dose_order = _integer_value(row.get("dose_order"), "dose_order")
            source_age = _integer_value(
                row.get("age_in_months"), "age_in_months"
            )
            if dose_order <= 0 or source_age < 0:
                raise ValueError("dose_order must be positive and age non-negative")
        except (TypeError, ValueError) as error:
            _rule_reject(
                result, "tbl_supplements", row, "S-03",
                str(error) or "dose_order and age_in_months must be integers",
            )
            continue
        supplement_type = str(row.get("supplement_type", "")).strip()
        if supplement_type not in {"Vitamin A", "Deworming"}:
            _rule_reject(
                result, "tbl_supplements", row, "S-06",
                "supplement_type is not an allowed source category",
            )
            continue
        try:
            derived_age = _age_in_months(
                date.fromisoformat(child["date_of_birth"]),
                administered,
            )
        except ValueError as error:
            _rule_reject(
                result, "tbl_supplements", row, "B-05", str(error)
            )
            continue
        _record_rule(result, "B-05")
        if source_age != derived_age:
            result.validations.append({
                "check_name": "source age consistency",
                "severity": "WARNING",
                "table_name": "tbl_supplements",
                "record_id": str(row["id"]),
                "message": (
                    "source age_in_months differs from DOB-derived age"
                ),
            })
        result.fact_supplement.append({
            "batch_id": batch_id,
            "run_id": result.run_id,
            "supplement_id": str(row["id"]),
            "child_key": child["child_key"],
            "date_administered": administered.isoformat(),
            "supplement_month": _month(administered),
            "supplement_type": supplement_type,
            "dose_order": dose_order,
            "age_months": derived_age,
        })

    trend_counts: Counter[Tuple[str, str, str, str]] = Counter()
    barangay_by_key = {
        child["child_key"]: child["barangay_name"]
        for child in result.dim_child
    }
    for fact in result.fact_assessment:
        barangay = barangay_by_key[fact["child_key"]]
        for indicator, source_column in INDICATORS:
            trend_counts[(
                barangay,
                fact["assessment_month"],
                indicator,
                fact[source_column],
            )] += 1
    result.fact_health_trends = [
        {
            "batch_id": batch_id,
            "run_id": result.run_id,
            "barangay_name": barangay,
            "assessment_month": month,
            "indicator": indicator,
            "nutritional_status": status,
            "total_count": total,
        }
        for (barangay, month, indicator, status), total in sorted(
            trend_counts.items()
        )
    ]
    result.rules_applied["B-04"] = len(result.fact_health_trends)

    accepted_counts = {
        "tbl_children": len(result.dim_child),
        "tbl_assessments": len(result.fact_assessment),
        "tbl_supplements": len(result.fact_supplement),
    }
    rejected_by_table = Counter(
        record["table_name"] for record in result.quarantine_records
    )
    for table_name in raw:
        metrics = result.metrics[table_name]
        metrics["records_output"] = accepted_counts[table_name]
        metrics["records_rejected"] = rejected_by_table[table_name]
        reconciles = (
            metrics["records_read"]
            == metrics["records_output"] + metrics["records_rejected"]
        )
        result.validations.append({
            "check_name": "record reconciliation",
            "severity": "CRITICAL",
            "table_name": table_name,
            "passed": reconciles,
            "message": (
                f"{metrics['records_read']} read = "
                f"{metrics['records_output']} output + "
                f"{metrics['records_rejected']} rejected"
            ),
        })
        business_rules_pass = (
            all(
                start_date <= date.fromisoformat(row["date_measured"]) < end_date
                and row["weight_kg"] > 0
                and row["height_cm"] > 0
                and row["age_months"] >= 0
                for row in result.fact_assessment
            )
            and all(
                start_date <= date.fromisoformat(row["date_administered"]) < end_date
                and row["dose_order"] > 0
                and row["age_months"] >= 0
                for row in result.fact_supplement
            )
            and all(row["barangay_name"] for row in result.dim_child)
        )
        result.validations.append({
            "check_name": "business rule and required dimension fields",
            "severity": "CRITICAL",
            "table_name": "transformed outputs",
            "passed": business_rules_pass,
            "message": "all output dates, measurements, ages, and barangays satisfy rules",
        })
    result.validations.extend([
        {
            "check_name": "key uniqueness",
            "severity": "CRITICAL",
            "table_name": table_name,
            "passed": len(keys) == len(set(keys)),
            "message": "target key duplicate count must be zero",
        }
        for table_name, keys in (
            ("dim_child", [row["child_key"] for row in result.dim_child]),
            ("fact_assessment", [row["assessment_id"] for row in result.fact_assessment]),
            ("fact_supplement", [row["supplement_id"] for row in result.fact_supplement]),
        )
    ])
    known_child_keys = {row["child_key"] for row in result.dim_child}
    for table_name, facts in (
        ("fact_assessment", result.fact_assessment),
        ("fact_supplement", result.fact_supplement),
    ):
        unresolved = sum(
            fact["child_key"] not in known_child_keys for fact in facts
        )
        result.validations.append({
            "check_name": "referential integrity",
            "severity": "CRITICAL",
            "table_name": table_name,
            "passed": unresolved == 0,
            "message": f"unresolved child_key count = {unresolved}",
        })
    expected_trend_count = len(result.fact_assessment) * len(INDICATORS)
    actual_trend_count = sum(
        row["total_count"] for row in result.fact_health_trends
    )
    result.validations.append({
        "check_name": "health trend aggregation reconciliation",
        "severity": "CRITICAL",
        "table_name": "fact_health_trends",
        "passed": actual_trend_count == expected_trend_count,
        "message": (
            f"{actual_trend_count} aggregated classifications = "
            f"{expected_trend_count} expected"
        ),
    })

    critical_failed = any(
        item.get("severity") == "CRITICAL" and item.get("passed") is False
        for item in result.validations
    )
    total_read = sum(item["records_read"] for item in result.metrics.values())
    total_rejected = sum(item["records_rejected"] for item in result.metrics.values())
    rejection_rate = total_rejected / total_read if total_read else 0.0
    if critical_failed:
        result.status = "REJECTED"
    elif total_read == 0 or rejection_rate >= 0.01 or any(
        item.get("severity") == "WARNING"
        for item in result.validations
    ):
        result.status = "MANUAL_REVIEW"
    else:
        result.status = "APPROVED"
    result.ended_at_utc = datetime.now(timezone.utc).isoformat()
    return result


def _standard_status(value: Any) -> str:
    if value is None or not str(value).strip():
        return "UNCLASSIFIED"
    return " ".join(str(value).split()).upper()


def transform_health_trends(
    assessments: Iterable[Mapping[str, Any]],
    children: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Compatibility helper for the chart-only aggregation API."""
    barangay_by_child: Dict[Any, str] = {}
    for child in children:
        child_id = child.get("id")
        barangay = child.get("barangay")
        if not child_id:
            raise ValueError("Child record is missing id")
        if not isinstance(barangay, str) or not barangay.strip():
            raise ValueError(f"Child {child_id!r} is missing barangay")
        if child_id in barangay_by_child:
            raise ValueError(f"Duplicate child id: {child_id!r}")
        barangay_by_child[child_id] = barangay

    counts: Counter[Tuple[str, str, str, str]] = Counter()
    seen_ids = set()
    for assessment in assessments:
        assessment_id = assessment.get("id")
        if not assessment_id:
            raise ValueError("Assessment record is missing id")
        if assessment_id in seen_ids:
            raise ValueError(f"Duplicate assessment id: {assessment_id!r}")
        seen_ids.add(assessment_id)
        child_id = assessment.get("child_id")
        if not child_id:
            raise ValueError(f"Assessment {assessment_id!r} is missing child_id")
        if child_id not in barangay_by_child:
            raise ValueError(
                f"Assessment {assessment_id!r} references an unknown child"
            )
        measured_date = _parse_date(assessment.get("date_measured"))
        for indicator, status_column in INDICATORS:
            status = assessment.get(status_column)
            if status is None or (
                isinstance(status, str) and not status.strip()
            ):
                status = "Unclassified"
            elif not isinstance(status, str):
                raise ValueError(
                    f"Assessment {assessment_id!r} has a non-text "
                    f"{status_column}"
                )
            counts[(
                barangay_by_child[child_id],
                _month(measured_date),
                indicator,
                status,
            )] += 1
    return [
        {
            "barangay_name": barangay,
            "assessment_month_year": month,
            "indicator": indicator,
            "nutritional_status": status,
            "total_count": total_count,
        }
        for (barangay, month, indicator, status), total_count in sorted(
            counts.items()
        )
    ]


def _is_invalid_positive_measurement(value: Any, column: str) -> bool:
    try:
        _positive_measurement(value, column)
    except ValueError:
        return True
    return False


def _is_future_date(value: Any, as_of_date: date) -> bool:
    try:
        return _parse_date(value) > as_of_date
    except ValueError:
        return False


def _is_valid_date(value: Any) -> bool:
    try:
        _parse_date(value)
    except ValueError:
        return False
    return True
