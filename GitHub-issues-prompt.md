# OpenCode Prompt: Automated GitHub Issues Creation

Copy and use this prompt in OpenCode or any AI coding assistant to automatically generate and push GitHub issues using the GitHub CLI (`gh`), compatible across all platforms (macOS, Linux, and Windows PowerShell/Git Bash).

---

## The Prompt to Copy & Paste

```markdown
You are an expert automation engineer and developer. Your task is to read the `github-issues.md` file in the current repository, parse the 7-day roadmap, and automatically create GitHub issues for each day (Day 1 through Day 7) using the GitHub CLI (`gh`).

### Instructions:
1. Check that the GitHub CLI is installed and authenticated (`gh auth status`). If not authenticated, prompt the user to run `gh auth login`.
2. Parse `github-issues.md` to extract each Day's title and its corresponding task checklist items.
3. For each day, create a GitHub issue using `gh issue create` with:
   - **Title**: The Day title (e.g., `Day 1: Project Setup & Environment Configuration`)
   - **Body**: The task checklist items under that day.
   - **Labels**: Add labels like `roadmap` or `etl`.
4. Handle cross-platform compatibility (works on Bash/Zsh on Linux/macOS and PowerShell/Git Bash on Windows).
5. Output a success message with links or titles of all created issues once finished.
```

---

## Cross-Platform Execution Script (Reference for Assistant / Shell)

If you need the assistant or script to run directly across platforms, use this robust Node.js or Python snippet, or platform-agnostic shell approach:

### Node.js Script (`create-issues.js`)
If Node.js is available across platforms, run `node create-issues.js`:

```javascript
const { execSync } = require('child_process');
const fs = require('fs');

try {
  const content = fs.readFileSync('github-issues.md', 'utf8');
  const days = content.split(/^## /m).slice(1);

  for (const dayBlock of days) {
    const lines = dayBlock.trim().split('\n');
    const title = lines[0].trim();
    const body = lines.slice(1).join('\n').trim();

    console.log(`Creating issue: ${title}`);
    const command = `gh issue create --title ${JSON.stringify(title)} --body ${JSON.stringify(body)} --label "roadmap,etl"`;
    execSync(command, { stdio: 'inherit' });
  }
  console.log('All issues created successfully!');
} catch (err) {
  console.error('Error creating issues:', err.message);
  process.exit(1);
}
```
