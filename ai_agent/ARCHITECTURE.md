# Architecture

## Overview

Government contract recompete monitoring platform.  Flask web app backed
by SQLite.  Autonomous AI engineering loop in ai_agent/.

## Components

- **app.py** — Flask routes and template rendering
- **db.py** — SQLite schema, ingest, FTS
- **analytics.py** — query layer (dashboard, vendor/agency profiles)
- **ai_agent/loop.py** — autonomous task execution loop
- **ai_agent/manager.py** — queue manager + LLM orchestration
- **ai_agent/recovery.py** — retry tracking and failure reports
- **ai_agent/eng_memory.py** — engineering knowledge documents
- **ai_agent/memory.py** — SQLite-backed code index (RepoMemory)
- **ai_agent/patcher.py** — patch application engine
- **ai_agent/reviewer.py** — dangerous-pattern safety check
