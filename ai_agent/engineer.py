import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
ENGINEER_LOG = LOG_DIR / "engineer.log"
FAILURES_LOG = LOG_DIR / "failures.log"

def log(message):
    LOG_DIR.mkdir(exist_ok=True)
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n"
    with ENGINEER_LOG.open("a") as f:
        f.write(line)
    print(line, end="", flush=True)

def run(cmd, check=False):
    log(f"RUN: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        log(result.stdout[-4000:])
    if result.stderr:
        log(result.stderr[-4000:])
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result

def read_file(name):
    path = ROOT / name
    return path.read_text() if path.exists() else ""

def main():
    log("Engineer supervisor smoke test started")

    task = read_file("TASK.md")
    handoff = read_file("HANDOFF.md")
    task_log = read_file("TASK_LOG.md")

    log(f"TASK.md chars: {len(task)}")
    log(f"HANDOFF.md chars: {len(handoff)}")
    log(f"TASK_LOG.md chars: {len(task_log)}")

    result = run(["bash", "-lc", "source .venv/bin/activate && pytest"], check=False)

    if result.returncode == 0:
        log("Tests passed. No commit made during smoke test.")
    else:
        with FAILURES_LOG.open("a") as f:
            f.write(f"\n[{datetime.now().isoformat()}] pytest failed\n")
            f.write(result.stdout)
            f.write(result.stderr)
        log("Tests failed. See logs/failures.log")

    log("Engineer supervisor smoke test finished")

if __name__ == "__main__":
    main()
