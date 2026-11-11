"""Run the synthetic classroom demo for the WeighToGo transformation."""

import csv
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

from pipelines.transformation.health_trends import (
    TransformationResult,
    save_transformation_result,
    transform_batch,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "demo" / "fixtures"
OUTPUT = ROOT / "data" / "demo-output"
BATCH_START = "2026-10-01"
BATCH_END = "2026-11-01"
AS_OF_DATE = date(2026, 10, 31)


def load_csv(filename: str) -> List[Dict[str, str]]:
    with (FIXTURES / filename).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def load_inputs() -> Dict[str, List[Dict[str, str]]]:
    return {
        "children": load_csv("tbl_children.csv"),
        "assessments": load_csv("tbl_assessments.csv"),
        "supplements": load_csv("tbl_supplements.csv"),
    }


def transform(
    inputs: Mapping[str, List[Mapping[str, Any]]],
    run_name: str,
) -> TransformationResult:
    return transform_batch(
        inputs["assessments"],
        inputs["children"],
        inputs["supplements"],
        parent_extraction_run_id=f"SYNTHETIC_DEMO_{run_name}",
        batch_start=BATCH_START,
        batch_end=BATCH_END,
        as_of_date=AS_OF_DATE,
    )


def show_result(name: str, result: TransformationResult) -> None:
    rejected = sum(
        metrics["records_rejected"] for metrics in result.metrics.values()
    )
    print(
        f"{name}: {result.status}; "
        f"input={sum(item['records_read'] for item in result.metrics.values())}; "
        f"output={sum(item['records_output'] for item in result.metrics.values())}; "
        f"rejected={rejected}"
    )
    for item in result.quarantine_records:
        print(
            f"  quarantine: table={item['table_name']} "
            f"id={item['source_record_id']} rule={item['rule_id']} "
            f"reason={item['reason']}"
        )
    for item in result.validations:
        if item.get("severity") == "WARNING":
            print(f"  warning: {item['check_name']}: {item['message']}")


def save_result(name: str, result: TransformationResult) -> None:
    saved_files = save_transformation_result(result, OUTPUT / name)
    print(f"  saved {len(saved_files)} CSV outputs to {OUTPUT / name}")


def expect(
    result: TransformationResult,
    expected_status: str,
    expected_rule: Optional[str],
    scenario_name: str,
) -> None:
    if result.status != expected_status:
        raise AssertionError(
            f"{scenario_name}: expected {expected_status}, got {result.status}"
        )
    found_rules = {item["rule_id"] for item in result.quarantine_records}
    if expected_rule is not None and expected_rule not in found_rules:
        raise AssertionError(
            f"{scenario_name}: expected quarantine rule {expected_rule}, "
            f"found {sorted(found_rules)}"
        )


def run_scenario(
    name: str,
    expected_status: str,
    expected_rule: Optional[str],
    mutate: Any,
) -> None:
    inputs = deepcopy(load_inputs())
    mutate(inputs)
    result = transform(inputs, name)
    expect(result, expected_status, expected_rule, name)
    show_result(name, result)
    save_result(name, result)


def set_negative_weight(inputs: MutableMapping[str, List[Dict[str, str]]]) -> None:
    inputs["assessments"][0]["weight"] = "-1"


def set_orphan_assessment(inputs: MutableMapping[str, List[Dict[str, str]]]) -> None:
    inputs["assessments"][0]["child_id"] = "00000000-0000-4000-8000-000000000000"


def add_tied_duplicate(inputs: MutableMapping[str, List[Dict[str, str]]]) -> None:
    inputs["assessments"].append(dict(inputs["assessments"][0]))


def remove_required_column(inputs: MutableMapping[str, List[Dict[str, str]]]) -> None:
    inputs["assessments"][0].pop("weight")


def set_age_mismatch(inputs: MutableMapping[str, List[Dict[str, str]]]) -> None:
    inputs["assessments"][0]["age_in_months"] = "1"


def set_out_of_window_date(
    inputs: MutableMapping[str, List[Dict[str, str]]],
) -> None:
    inputs["assessments"][0]["date_measured"] = BATCH_END


def set_future_supplement_date(
    inputs: MutableMapping[str, List[Dict[str, str]]],
) -> None:
    inputs["supplements"][0]["date_administered"] = "2026-11-01"


def set_unsupported_supplement(
    inputs: MutableMapping[str, List[Dict[str, str]]],
) -> None:
    inputs["supplements"][0]["supplement_type"] = "Multivitamin"


def main() -> None:
    print("WeighToGo synthetic transformation demo")
    print(f"Batch window: [{BATCH_START}, {BATCH_END}); as-of date: {AS_OF_DATE}")
    print("No live Supabase connection is used; all inputs are synthetic CSVs.\n")

    clean_result = transform(load_inputs(), "clean")
    expect(clean_result, "APPROVED", None, "clean")
    if clean_result.quarantine_records:
        raise AssertionError("Clean demo data unexpectedly produced quarantine rows")
    if sum(row["total_count"] for row in clean_result.fact_health_trends) != (
        3 * len(clean_result.fact_assessment)
    ):
        raise AssertionError("Health-trend aggregation did not reconcile")
    show_result("clean", clean_result)
    print(
        f"  accepted assessments={len(clean_result.fact_assessment)}; "
        f"supplements={len(clean_result.fact_supplement)}; "
        f"trend count total="
        f"{sum(row['total_count'] for row in clean_result.fact_health_trends)}"
    )
    save_result("clean", clean_result)

    scenarios = [
        ("negative-weight", "MANUAL_REVIEW", "C-02", set_negative_weight),
        ("orphan-assessment", "MANUAL_REVIEW", "B-01", set_orphan_assessment),
        ("tied-duplicate", "MANUAL_REVIEW", "C-04", add_tied_duplicate),
        ("missing-column", "REJECTED", "S-05", remove_required_column),
        ("age-mismatch", "MANUAL_REVIEW", None, set_age_mismatch),
        ("outside-window", "MANUAL_REVIEW", "B-02", set_out_of_window_date),
        ("future-supplement", "MANUAL_REVIEW", "C-03", set_future_supplement_date),
        ("unsupported-supplement", "MANUAL_REVIEW", "S-06", set_unsupported_supplement),
    ]
    print("\nValidation scenarios (each starts from a fresh copy of the clean CSVs):")
    for scenario in scenarios:
        run_scenario(*scenario)

    print(f"\nDEMO PASSED. Review generated reports under: {OUTPUT}")


if __name__ == "__main__":
    main()
