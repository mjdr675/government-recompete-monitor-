#!/usr/bin/env bash
set -e

cd ~/government-recompete-monitor-
source .venv/bin/activate

tmux has-session -t engineer 2>/dev/null && tmux attach -t engineer || tmux new -s engineer
