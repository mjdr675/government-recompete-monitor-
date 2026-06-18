# AI Agent

A minimal, safe coding agent scaffold for `government-recompete-monitor`.

The agent reads tasks from `TASK.md`, generates a plan via an AI API,
applies edits, runs tests, commits, and logs a summary to `HANDOFF.md`.

## How it works

```
TASK.md  ──► agent reads next OPEN task
         ──► sends task + git context to AI API  ← (stub until API key added)
         ──► prints plan
         ──► (if DRY_RUN=false) applies edits, runs tests, commits
         ──► appends summary to HANDOFF.md
```

## Setup

```bash
cp ai_agent/.env.example ai_agent/.env
# Edit ai_agent/.env and add your ANTHROPIC_API_KEY
pip install anthropic          # or: pip install openai
```

## Run (dry-run, safe)

```bash
DRY_RUN=true python ai_agent/agent.py
```

## Run (live — edits + commits)

```bash
git checkout -b ai-agent       # agent only commits to this branch
DRY_RUN=false python ai_agent/agent.py
```

## Safety guardrails

The agent will refuse any command matching:

| Pattern | Reason |
|---|---|
| `git push` | Never auto-pushes |
| `rm -rf` | No destructive deletes |
| `.env` | Never reads secrets |
| `DROP TABLE` | No destructive SQL |
| `sk-` / API key patterns | Never logs secrets |

It also checks the current git branch and refuses to commit unless it matches
`AGENT_BRANCH` (default: `ai-agent`).

## Running on a VPS with cron (every 5 hours)

```bash
# On your VPS, clone the repo and set up the env:
git clone https://github.com/mjdr675/government-recompete-monitor- /opt/recompete
cd /opt/recompete
pip install -r requirements.txt anthropic

cp ai_agent/.env.example ai_agent/.env
# Edit /opt/recompete/ai_agent/.env with your API key

# Add to crontab (runs at 0, 5, 10, 15, 20 hours UTC):
crontab -e
```

```cron
0 */5 * * * cd /opt/recompete && DRY_RUN=false AGENT_BRANCH=ai-agent python ai_agent/agent.py >> /var/log/recompete-agent.log 2>&1
```

To review what the agent did each run, check:
- `HANDOFF.md` — human-readable summary of every run
- `/var/log/recompete-agent.log` — full stdout/stderr log
- `git log ai-agent` — all commits the agent made

## Connecting an AI API

Open `ai_agent/agent.py` and find the `plan_task()` function.
Replace the stub block with:

**Anthropic:**
```python
import anthropic
client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env
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
client = OpenAI()                # reads OPENAI_API_KEY from env
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}],
)
return response.choices[0].message.content
```
