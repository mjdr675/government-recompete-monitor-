#!/usr/bin/env bash
cd "$(dirname "$0")"

echo
echo "==== Git ===="
git status

echo
echo "==== Latest Commit ===="
git log --oneline -5

echo
echo "==== Tests ===="
source .venv/bin/activate
pytest -q
