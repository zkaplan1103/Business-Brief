# Memory INDEX — read this first, then load only your tagged file(s)

Append-only, dated notes. Each subagent reads only the file matching its tag,
then appends what it learned. Keeps context small as the project grows.

| Tag | File | Owner |
|------|------|-------|
| `decisions` | `00-decisions.md` | everyone (one line per meaningful decision) |
| `data` | `01-data.md` | data-engineer |
| `analysis` | `02-analysis.md` | analysis-engineer |
| `brief` | `03-brief.md` | brief-engineer |
| `ui` | `04-ui.md` | ui-engineer |
| `eval` | `05-eval.md` | eval-engineer |
| `security` | `06-security.md` | security-engineer (red-team files to `red-team-findings.md`) |
| `cost` | `02-analysis.md` | cost-engineer (shares the analysis log) |

Protocol: before work → read INDEX + your tagged file. After work → append a
dated entry to your tagged file + one line to `00-decisions.md`. Never edit
another agent's file; never load a file whose tag isn't yours.
