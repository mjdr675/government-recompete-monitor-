# AI Agent System

A minimal, safe multi-agent coding scaffold for `government-recompete-monitor`.

## How it works

```
agent.py          ← entry point (safety checks, git state, DRY_RUN gate)
  └── manager.py  ← reads backlog, picks highest-priority task, assigns role
        ├── backend_engineer.py   ← Flask / SQLite / Python tasks
        ├── frontend_engineer.py  ← Jinja2 / HTML / CSS tasks
        ├── qa_engineer.py        ← pytest / test coverage tasks
        ├── devops_engineer.py    ← Railway / gunicorn / VPS tasks
        └── docs_writer.py        ← README / docstring tasks
```

**Task priority order (manager reads these in sequence):**
1. `backlog/critical.md` — blocking / security issues
2. `backlog/bugs.md` — confirmed bugs
3. `backlog/high.md` — important features
4. `backlog/medium.md` — polish and improvements
5. `TASK.md` — general queue
6. `backlog/ideas.md` — **never auto-picked** (humans promote manually)

The manager picks the first `[OPEN]` task it finds, assigns it to the right
specialist, gets a plan, and logs everything to `HANDOFF.md` and `TASK_LOG.md`.

## Setup

```bash
cp ai_agent/.env.example ai_agent/.env
# Edit ai_agent/.env — add ANTHROPIC_API_KEY or OPENAI_API_KEY
pip install anthropic          # or: pip install openai
```

## Run (dry-run — safe, plan only)

```bash
DRY_RUN=true python ai_agent/agent.py
```

## Run (live — edits + commits)

```bash
git checkout -b ai-agent       # agent only commits to this branch
DRY_RUN=false python ai_agent/agent.py
```

## Adding tasks

Add a task to the right backlog file:

```markdown
### [OPEN] Short title
Description of what to do.
Role: backend | frontend | qa | devops | docs
```

Save the file — the agent picks it up on the next run.

To promote an idea from `backlog/ideas.md`, copy its block into
`backlog/high.md` or `backlog/medium.md` and change `[IDEA]` to `[OPEN]`.

## Marking tasks done

Change `[OPEN]` to `[DONE]` in the backlog file after a task is completed.
The agent skips `[DONE]`, `[IN_PROGRESS]`, and `[SKIPPED]` tasks.

## Logs

| File | Contents |
|---|---|
| `HANDOFF.md` | Full plan narrative for each run |
| `TASK_LOG.md` | One-line table row per run (timestamp, role, task, outcome) |

## Safety guardrails

The agent refuses any command matching:

| Pattern | Reason |
|---|---|
| `git push` | Never auto-pushes |
| `rm -rf` | No destructive deletes |
| `.env` | Never reads secrets |
| `DROP TABLE` | No destructive SQL |
| `sk-` / API key patterns | Never logs secrets |

In non-dry-run mode it also checks the current branch matches `AGENT_BRANCH`
(default: `ai-agent`) and refuses to commit to `main`.

## Running on a VPS with cron (every 5 hours)

```bash
# On your VPS:
git clone https://github.com/mjdr675/government-recompete-monitor- /opt/recompete
cd /opt/recompete
pip install -r requirements.txt anthropic

cp ai_agent/.env.example ai_agent/.env
# Edit /opt/recompete/ai_agent/.env — add your API key

# Create the agent branch once:
git checkout -b ai-agent
git push -u origin ai-agent

# Add to crontab (every 5 hours):
crontab -e
```

```cron
0 */5 * * * cd /opt/recompete && git pull origin ai-agent && DRY_RUN=false AGENT_BRANCH=ai-agent python ai_agent/agent.py >> /var/log/recompete-agent.log 2>&1
```

## Connecting an AI API

Open `ai_agent/backend_engineer.py` (or whichever specialist) and replace the
stub in `plan()` with a real API call:

**Anthropic:**
```python
import anthropic
client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}],
)
return message.content[0].text
```

**OpenAI:**
```python
from openai import OpenAI
client = OpenAI()                # reads OPENAI_API_KEY
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}],
)
return response.choices[0].message.content
```

Do the same for each specialist. Each has its own role-specific prompt already
drafted in the docstring.
