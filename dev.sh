#!/bin/sh
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmux new-session -d -s kizuna -n backend -c "$root/backend" 'uv run uvicorn app.main:app --reload'
tmux new-window -t kizuna -n frontend -c "$root/frontend" 'pnpm dev'
tmux attach -t kizuna
