# GitHub Issues Automation Prompt

This prompt and guide instruct you on how to automatically create GitHub Issues from your `github-issues.md` file using the GitHub CLI (`gh`).

---

## Prerequisites
1. Ensure you have the **GitHub CLI** installed and authenticated:
   ```bash
   gh auth status
   ```
   *(If not authenticated, run `gh auth login`)*
2. Ensure you are inside your local repository directory containing `github-issues.md`.

---

## Automated Script (Bash)

Run the following bash script in your terminal to parse `github-issues.md` and automatically create GitHub issues with appropriate titles, descriptions, and labels for Days 1 through 7:

```bash
#!/bin/bash

# Ensure github-issues.md exists
if [ ! -f "github-issues.md" ]; then
  echo "github-issues.md not found!"
  exit 1
fi

# Use awk to parse Day headers and tasks, then create GitHub issues using gh CLI
awk '
/^## Day [0-9]+:/ {
  if (title != "") {
    print title "|" body
  }
  title = $0
  sub(/^## /, "", title)
  body = ""
  next
}
{
  if (title != "") {
    body = body $0 "\n"
  }
}
END {
  if (title != "") {
    print title "|" body
  }
}
' github-issues.md | while IFS="|" read -r issue_title issue_body; do
  echo "Creating issue: $issue_title"
  gh issue create --title "$issue_title" --body "$issue_body" --label "roadmap,etl"
done

echo "All GitHub issues created successfully!"
```

---

## Manual `gh` Commands

If you prefer creating them one by one using the GitHub CLI:

```bash
gh issue create --title "Day 1: Project Setup & Environment Configuration" --body "$(cat <<'EOF'
- [ ] Initialize Repository & Project Structure
- [ ] Define Data Schemas & Sources
EOF
)" --label "roadmap"

gh issue create --title "Day 2: Extraction Phase Implementation" --body "$(cat <<'EOF'
- [ ] Develop Raw Data Extractors (`extraction/extractor.py`)
- [ ] Write Extraction Unit Tests (`extraction/test_extractor.py`)
EOF
)" --label "roadmap"

gh issue create --title "Day 3: Transformation Phase & Business Logic" --body "$(cat <<'EOF'
- [ ] Build Data Cleaning & Transformation Scripts
- [ ] Validate Transformed Data
EOF
)" --label "roadmap"

gh issue create --title "Day 4: Loading Phase & Storage Integration" --body "$(cat <<'EOF'
- [ ] Implement Target Loader (`pipelines/extractor.py` / loader modules)
- [ ] End-to-End Pipeline Integration (`pipelines/lab3.py`)
EOF
)" --label "roadmap"

gh issue create --title "Day 5: Error Handling, Logging & Monitoring" --body "$(cat <<'EOF'
- [ ] Implement Structured Logging
- [ ] Add Exception Handling & Retries
EOF
)" --label "roadmap"

gh issue create --title "Day 6: Automation & Scheduling" --body "$(cat <<'EOF'
- [ ] Configure Cron / Airflow / GitHub Actions
- [ ] Environment Secret Management
EOF
)" --label "roadmap"

gh issue create --title "Day 7: Documentation, Polish & Final Review" --body "$(cat <<'EOF'
- [ ] Complete System Documentation (`docs/`)
- [ ] Final Code Cleanup & End-to-End Dry Run
EOF
)" --label "roadmap"
```
