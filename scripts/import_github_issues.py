#!/usr/bin/env python3
"""Import the WeighToGo roadmap into GitHub issues.

Run this while authenticated as the account that should author the issues:

    gh auth login
    gh auth switch --user lopezrnl
    python scripts/import_github_issues.py

The script is idempotent: issues whose title already exists are skipped, and
milestones/labels are created only when missing. Delete the script afterwards
if you do not want to keep it in the repository.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REPO = "ArizalaRonAndrew/WeighToGo-ETL-Pipeline"
DEFAULT_AUTHOR = "lopezrnl"


def find_gh() -> str:
    found = shutil.which("gh")
    if found:
        return found
    windows_default = Path(r"C:\Program Files\GitHub CLI\gh.exe")
    if windows_default.exists():
        return str(windows_default)
    raise SystemExit(
        "GitHub CLI (gh) was not found. Install it from https://cli.github.com/ and retry."
    )


GH = find_gh()
REPO = DEFAULT_REPO


def gh(*args: str, body: str | None = None) -> str:
    cmd = [GH, *args]
    result = subprocess.run(
        cmd,
        input=body,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


DAYS = [
    ("Day 1", "Project Setup & Environment Configuration", "2026-10-26"),
    ("Day 2", "Extraction Phase Implementation", "2026-10-27"),
    ("Day 3", "Transformation Phase & Business Logic", "2026-10-28"),
    ("Day 4", "Loading Phase & Storage Integration", "2026-10-29"),
    ("Day 5", "Error Handling, Logging & Monitoring", "2026-10-30"),
    ("Day 6", "Automation & Scheduling", "2026-10-31"),
    ("Day 7", "Documentation, Polish & Final Review", "2026-11-01"),
]

LABELS = {
    "day-1": ("1d76db", "Day 1 - Project setup and environment configuration"),
    "day-2": ("0e8a16", "Day 2 - Extraction phase implementation"),
    "day-3": ("fbca04", "Day 3 - Transformation phase and business logic"),
    "day-4": ("5319e7", "Day 4 - Loading phase and storage integration"),
    "day-5": ("d93f0b", "Day 5 - Error handling, logging and monitoring"),
    "day-6": ("d4c5f9", "Day 6 - Automation and scheduling"),
    "day-7": ("0075ca", "Day 7 - Documentation, polish and final review"),
    "extraction": ("c5def5", "Data extraction stage"),
    "transformation": ("fef2c0", "Data cleaning and transformation stage"),
    "loading": ("bfdadc", "Target loading and storage"),
    "testing": ("c2e0c6", "Automated tests and validation"),
    "logging": ("bfd4f2", "Structured logging and observability"),
    "automation": ("e4e669", "Scheduling and CI/CD automation"),
    "documentation": ("0052cc", "Documentation and handover material"),
    "security": ("b60205", "Secrets and credential management"),
}


@dataclass
class Issue:
    title: str
    day: int
    labels: list[str]
    context: str
    tasks: list[str]
    acceptance: list[str]
    references: list[str] = field(default_factory=list)

    def body(self) -> str:
        lines = [
            "## Context",
            "",
            self.context,
            "",
            "## Tasks",
            "",
            *[f"- [ ] {task}" for task in self.tasks],
            "",
            "## Acceptance criteria",
            "",
            *[f"- [ ] {criterion}" for criterion in self.acceptance],
        ]
        if self.references:
            lines += ["", "## References", "", *[f"- {ref}" for ref in self.references]]
        lines += [
            "",
            "---",
            f"_Roadmap source: `github.issues.md` (Day {self.day})._",
        ]
        return "\n".join(lines)


ISSUES = [
    Issue(
        title="Initialize Repository & Project Structure",
        day=1,
        labels=["day-1", "documentation"],
        context=(
            "Bootstrap the repository skeleton that every pipeline stage builds on: "
            "packages for extraction, pipelines, docs and tests, pinned dependencies, "
            "and a virtual environment workflow."
        ),
        tasks=[
            "Create `extraction/`, `pipelines/`, `docs/` and `tests/` directories with `__init__.py` where needed",
            "Add `.gitignore` covering `.env`, virtualenvs, caches, logs and local databases",
            "Add `requirements.txt` with runtime and test dependencies",
            "Document virtual environment creation and dependency installation in the README",
            "Preserve the existing `docs/extraction/lab3.md` extraction specification",
        ],
        acceptance=[
            "A fresh clone can create `.venv` and install dependencies from `requirements.txt`",
            "No secrets, virtualenv contents, logs or local databases are tracked by git",
            "`python -m pytest` collects the test suite from the repository root",
        ],
        references=["`docs/extraction/lab3.md`", "`README.md`"],
    ),
    Issue(
        title="Define Data Schemas & Sources",
        day=1,
        labels=["day-1", "extraction", "documentation"],
        context=(
            "Document the input contracts (Supabase/PostgreSQL operational tables) and the "
            "target/staging schemas so extraction, transformation and loading agree on "
            "column names, types and keys."
        ),
        tasks=[
            "Document the source tables `children`, `assessment` and `supplements` with column types and keys",
            "Define staging and final target schemas for weight and health metrics",
            "Record the 1:1 snake_case mapping rules from the source data contract",
            "Add SQL bootstrap scripts or metadata definitions for the target tables",
        ],
        acceptance=[
            "Source columns, types and relationships are documented in `docs/`",
            "Target tables are defined in code (SQLAlchemy metadata) and documented",
            "Primary keys, foreign keys and date/numeric columns match `docs/extraction/lab3.md`",
        ],
        references=["`docs/extraction/lab3.md#2-source-tables-and-column-specification`"],
    ),
    Issue(
        title="Develop Raw Data Extractors (`extraction/extractor.py`)",
        day=2,
        labels=["day-2", "extraction"],
        context=(
            "Implement modular extractors that pull raw records from Supabase/PostgreSQL for "
            "the selected monthly processing period, with authentication, pagination, "
            "record-count validation and retries."
        ),
        tasks=[
            "Implement a paginated Supabase REST client with auth headers and configurable page size",
            "Add retry/backoff handling for network failures and transient HTTP errors",
            "Extract `children`, `assessment` and `supplements` for the target month",
            "Validate source counts and required `id` / `child_id` identifiers",
            "Emit structured extraction metadata (run ID, period, table, duration, record count, status)",
        ],
        acceptance=[
            "Extraction handles multi-page responses without dropping or duplicating rows",
            "Counts from the source match the extracted records or the run fails with a clear error",
            "Records with missing identifiers cause a validation failure before loading",
        ],
        references=["`docs/extraction/lab3.md#3-extraction-validation-and-data-quality-checks`"],
    ),
    Issue(
        title="Write Extraction Unit Tests (`extraction/test_extractor.py`)",
        day=2,
        labels=["day-2", "testing", "extraction"],
        context=(
            "Cover the extraction stage with fast, deterministic tests using mocks so network "
            "access and production credentials are never required in CI."
        ),
        tasks=[
            "Test successful paginated extraction for every source table",
            "Test authentication headers and period filters",
            "Test malformed responses, HTTP errors and unreachable endpoints",
            "Test count mismatches, missing identifiers and empty monthly periods",
        ],
        acceptance=[
            "`python -m pytest extraction/test_extractor.py` passes without network access",
            "Failure paths assert the correct exception type and message",
            "No real Supabase credentials are used by the test suite",
        ],
        references=["`extraction/extractor.py`"],
    ),
    Issue(
        title="Build Data Cleaning & Transformation Scripts",
        day=3,
        labels=["day-3", "transformation"],
        context=(
            "Convert validated raw records into analytics-ready data: remove duplicates, "
            "handle missing values, normalize weight units and timestamps, and derive "
            "age in months."
        ),
        tasks=[
            "Implement transformations in `pipelines/transform.py`",
            "Drop or reject rows with missing critical fields and deduplicate by primary key",
            "Normalize weight units (lbs to kg) and standardize dates/timestamps",
            "Derive `age_in_months` from date of birth when missing",
            "Normalize categorical values such as gender and nutrition statuses",
            "Track rejected records with reasons for the run summary",
        ],
        acceptance=[
            "Duplicate IDs collapse to a single deterministic record",
            "Weights are stored in kilograms and dates are ISO-8601 dates",
            "Every rejected row has a machine-readable reason in the run summary",
        ],
        references=["`docs/extraction/lab3.md#6-extraction-data-contract-and-naming-convention`"],
    ),
    Issue(
        title="Validate Transformed Data",
        day=3,
        labels=["day-3", "transformation", "testing"],
        context=(
            "Add data-integrity checks between transformation and loading so corrupt or "
            "incomplete batches never reach the target warehouse."
        ),
        tasks=[
            "Validate unique primary keys across all transformed datasets",
            "Validate non-null foreign keys and referential integrity to `children`",
            "Validate physiological ranges for weight, height and age",
            "Detect duplicate measurements and future-dated records",
            "Fail the run with a non-zero exit code and actionable log message on violations",
        ],
        acceptance=[
            "Invalid batches raise a validation error before any target write",
            "Validation failures report the offending table, column and record count",
            "Valid batches pass with zero violations",
        ],
        references=["`docs/extraction/lab3.md#7-extraction-acceptance-and-handover-rules`"],
    ),
    Issue(
        title="Implement Target Loader (`pipelines/loader.py`)",
        day=4,
        labels=["day-4", "loading"],
        context=(
            "Load transformed data into the target destination (PostgreSQL/Supabase or SQLite "
            "for local runs) idempotently, so re-running a batch never duplicates rows."
        ),
        tasks=[
            "Create target/staging table metadata and schema creation helpers",
            "Load raw records into staging tables after extraction",
            "Upsert transformed records into final `children`, `assessment` and `supplements` tables",
            "Make loads idempotent with `ON CONFLICT` upserts on primary keys",
            "Record per-run load counts in `pipeline_runs`",
        ],
        acceptance=[
            "Running the same batch twice leaves row counts unchanged",
            "Updated source values replace existing target values",
            "Loads are transactional and roll back completely on failure",
        ],
        references=["`docs/extraction/lab3.md#7-extraction-acceptance-and-handover-rules`"],
    ),
    Issue(
        title="End-to-End Pipeline Integration (`pipelines/lab3.py`)",
        day=4,
        labels=["day-4", "loading", "automation"],
        context=(
            "Wire extraction, validation, transformation and loading into one runnable "
            "pipeline script with clear CLI options, run metadata and exit codes."
        ),
        tasks=[
            "Implement the entry point `python -m pipelines.lab3`",
            "Support `--period`, `--barangay`, `--dry-run` and `--source-json` options",
            "Connect extract to validate, transform, validate and load stages",
            "Print and persist a JSON run summary (run ID, counts, status, duration)",
            "Return documented exit codes for config, extraction, manual review and load failures",
        ],
        acceptance=[
            "A local end-to-end run against JSON fixtures and SQLite completes with exit code 0",
            "`--dry-run` performs extraction and transformation without writing to the target",
            "The run summary and `pipeline_runs` row agree on record counts and status",
        ],
        references=["`docs/extraction/lab3.md`"],
    ),
    Issue(
        title="Implement Structured Logging",
        day=5,
        labels=["day-5", "logging"],
        context=(
            "Add structured JSON logging across every stage, including run ID, period, table, "
            "record counts, durations and errors, with retention-friendly rotation."
        ),
        tasks=[
            "Add a JSON formatter and rotating file handler in `pipelines/logging_conf.py`",
            "Log start/end events for each pipeline stage with duration and status",
            "Include run ID, target period, table name and record counts in log records",
            "Log rejected rows and validation problems at WARNING level",
            "Keep console output human-readable enough for local runs",
        ],
        acceptance=[
            "Every stage emits start and completion events with the run ID",
            "Log files rotate and are written under `logs/` (ignored by git)",
            "Errors are logged once with a stack trace and a stable error code",
        ],
        references=["`docs/extraction/lab3.md#4-extraction-metadata-and-log-specification`"],
    ),
    Issue(
        title="Add Exception Handling & Retries",
        day=5,
        labels=["day-5", "logging", "extraction"],
        context=(
            "Wrap pipeline stages in explicit error handling, add bounded retries for "
            "transient failures, and translate failures into clean exit codes and "
            "operator-friendly messages."
        ),
        tasks=[
            "Define pipeline exception types with stable exit codes",
            "Add exponential-backoff retries for transient network and database errors",
            "Catch manual-review conditions (for example an empty barangay month) separately",
            "Persist failed-run status and error message to `pipeline_runs`",
            "Avoid leaking secrets in logs and exception messages",
        ],
        acceptance=[
            "Transient failures retry a bounded number of times before failing",
            "Each failure mode maps to a documented non-zero exit code",
            "No credentials appear in logs, summaries or error output",
        ],
        references=["`docs/extraction/lab3.md#8-common-extraction-problems-and-mitigation`"],
    ),
    Issue(
        title="Configure Cron / Airflow / GitHub Actions",
        day=6,
        labels=["day-6", "automation"],
        context=(
            "Automate the pipeline with GitHub Actions: run tests on every push, then execute "
            "the monthly batch on a schedule with manual dispatch support."
        ),
        tasks=[
            "Add `.github/workflows/etl.yml` with `schedule` and `workflow_dispatch` triggers",
            "Run the test suite before the pipeline job",
            "Pass the target period and optional barangay through workflow inputs",
            "Upload logs and the JSON run summary as workflow artifacts",
            "Document local cron/Task Scheduler usage as an alternative",
        ],
        acceptance=[
            "The workflow runs tests and the pipeline on a schedule",
            "Manual runs accept a target period and dry-run flag",
            "Failed runs surface a non-zero exit code and keep logs as artifacts",
        ],
        references=["`.github/workflows/etl.yml`"],
    ),
    Issue(
        title="Environment Secret Management",
        day=6,
        labels=["day-6", "security", "automation"],
        context=(
            "Keep database credentials and Supabase keys out of source control while making "
            "local and CI configuration explicit and reproducible."
        ),
        tasks=[
            "Add `.env.example` documenting every required variable",
            "Load configuration from environment variables with validation at startup",
            "Store production secrets in GitHub Actions repository secrets",
            "Ensure `.env` is git-ignored and fail fast when required variables are missing",
            "Document Supabase key usage (anon vs service role) and least-privilege access",
        ],
        acceptance=[
            "`.env` is never tracked and `.env.example` lists all supported variables",
            "The pipeline fails with a clear configuration error when required values are absent",
            "GitHub Actions reads credentials only from secrets",
        ],
        references=["`.env.example`", "`docs/setup.md`"],
    ),
    Issue(
        title="Complete System Documentation (`docs/`)",
        day=7,
        labels=["day-7", "documentation"],
        context=(
            "Produce the handover package: setup guide, architecture overview, data contracts, "
            "operations runbook and troubleshooting instructions."
        ),
        tasks=[
            "Write `README.md` with quick start and project layout",
            "Write `docs/setup.md`, `docs/architecture.md`, `docs/schemas.md` and `docs/operations.md`",
            "Write `docs/troubleshooting.md` covering known extraction and loading failures",
            "Document the runbook for re-running a month and reading logs",
        ],
        acceptance=[
            "A new developer can set up, test and run the pipeline using only the docs",
            "Architecture diagrams (Mermaid) match the implemented modules",
            "Troubleshooting entries map symptoms to concrete fixes",
        ],
        references=["`docs/extraction/lab3.md`"],
    ),
    Issue(
        title="Final Code Cleanup & End-to-End Dry Run",
        day=7,
        labels=["day-7", "testing", "documentation"],
        context=(
            "Perform the final quality pass: run the full suite, execute a clean end-to-end "
            "dry run, confirm idempotency, and close out the roadmap checklist."
        ),
        tasks=[
            "Run `python -m pytest` and fix any failures or warnings",
            "Execute a clean dry run against fixtures and a full local run against SQLite",
            "Verify target row counts, rejected-row summary and `pipeline_runs` output",
            "Re-run the same batch to confirm idempotency",
            "Update `github.issues.md` and close completed issues",
        ],
        acceptance=[
            "All tests pass from a fresh virtual environment",
            "The dry run and full run produce consistent summaries",
            "Re-running a batch creates no duplicates",
        ],
        references=["`README.md`", "`github.issues.md`"],
    ),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the WeighToGo roadmap issues with the authenticated GitHub account."
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name of the target repository")
    parser.add_argument(
        "--author",
        default=DEFAULT_AUTHOR,
        help="GitHub login that must be authenticated before anything is created",
    )
    parser.add_argument(
        "--assignee",
        default=None,
        help="Login to assign the issues to (defaults to --author)",
    )
    parser.add_argument(
        "--index-file",
        default="docs/github-issues.md",
        help="Markdown file that receives a table of created issue links",
    )
    parser.add_argument("--dry-run", action="store_true", help="show what would be created")
    parser.add_argument(
        "--allow-any-author",
        action="store_true",
        help="skip the authenticated-user safety check (for testing only)",
    )
    return parser.parse_args(argv)


def current_login() -> str:
    return gh("api", "user", "--jq", ".login")


def load_existing_issues() -> dict[str, dict]:
    payload = json.loads(gh("api", f"repos/{REPO}/issues?state=all&per_page=100"))
    return {item["title"]: item for item in payload if "pull_request" not in item}


def write_index(rows: list[tuple[str, int, str, str]], path: Path) -> None:
    lines = [
        "# GitHub Issue Index",
        "",
        "Generated by `scripts/import_github_issues.py` from `github.issues.md`.",
        "",
        "| Day | Issue | Title |",
        "| :-- | :---- | :---- |",
    ]
    lines += [f"| {day} | [#{number}]({url}) | {title} |" for day, number, title, url in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    global REPO

    args = parse_args(argv)
    REPO = args.repo
    assignee = args.assignee or args.author
    index_path = Path(args.index_file)

    login = current_login()
    if not args.allow_any_author and login.lower() != args.author.lower():
        print(
            f"Refusing to create issues: gh is authenticated as '{login}' but the expected "
            f"author is '{args.author}'.",
            file=sys.stderr,
        )
        print(f"Switch accounts with: gh auth switch --user {args.author}", file=sys.stderr)
        return 2

    print(f"Authenticated as {login}; target repository: {REPO}")

    existing_milestones = json.loads(
        gh("api", f"repos/{REPO}/milestones?state=all&per_page=100")
    )
    milestone_titles = {m["title"] for m in existing_milestones}
    existing_issues = load_existing_issues()
    existing_labels = {
        label["name"]
        for label in json.loads(gh("api", f"repos/{REPO}/labels?per_page=100"))
    }

    for day, title, due in DAYS:
        milestone_title = f"{day}: {title}"
        if milestone_title in milestone_titles:
            print(f"milestone exists: {milestone_title}")
            continue
        if args.dry_run:
            print(f"[dry-run] would create milestone: {milestone_title}")
            continue
        gh(
            "api",
            f"repos/{REPO}/milestones",
            "-f",
            f"title={milestone_title}",
            "-f",
            f"description={day} of the WeighToGo ETL 7-day roadmap.",
            "-f",
            f"due_on={due}T17:00:00Z",
        )
        print(f"created milestone: {milestone_title}")

    for name, (color, description) in LABELS.items():
        if name in existing_labels:
            continue
        if args.dry_run:
            print(f"[dry-run] would create label: {name}")
            continue
        gh("label", "create", name, "--color", color, "--description", description, "--force")
        print(f"created label: {name}")

    created: list[tuple[str, int, str]] = []
    for issue in ISSUES:
        milestone = f"Day {issue.day}: {DAYS[issue.day - 1][1]}"
        if issue.title in existing_issues:
            number = int(existing_issues[issue.title]["number"])
            print(f"issue exists, skipping: #{number} {issue.title}")
            continue
        if args.dry_run:
            print(f"[dry-run] would create: {issue.title} ({milestone}, assignee {assignee})")
            continue

        create_args = [
            "issue",
            "create",
            "--repo",
            REPO,
            "--title",
            issue.title,
            "--body-file",
            "-",
            "--milestone",
            milestone,
            "--assignee",
            assignee,
        ]
        for label in issue.labels:
            create_args += ["--label", label]
        url = gh(*create_args, body=issue.body())
        number = int(url.rstrip("/").rsplit("/", 1)[1])
        created.append((issue.title, number, url))
        print(f"created #{number}: {issue.title}")

    if args.dry_run:
        print("Dry run complete. Nothing was created.")
        return 0

    if created:
        existing_issues = load_existing_issues()
    index_rows: list[tuple[str, int, str, str]] = []
    for issue in ISSUES:
        item = existing_issues.get(issue.title)
        if item is None:
            continue
        index_rows.append(
            (
                f"Day {issue.day}",
                int(item["number"]),
                issue.title,
                item["html_url"],
            )
        )
    write_index(index_rows, index_path)
    print(f"wrote issue index: {index_path}")

    print(
        json.dumps(
            [{"title": t, "number": n, "url": u} for t, n, u in created],
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
