# Kizuna Backend

FastAPI backend for Kizuna.

## Development

Run the backend directly during local development:

```sh
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

> **Hot-reload CPU warning:** `uvicorn --reload` uses `watchfiles` for efficient reloading.
> If `watchfiles` is not installed it falls back to `StatReload`, which polls the entire
> `backend/` tree every 0.25 s. Because `.venv/` (~300 MB, thousands of files) lives there,
> this can pin 20-40% of a CPU and generate constant filesystem churn (which also triggers
> Spotlight reindexing and background disk I/O).
>
> Install the watcher, or scope what gets watched:
>
> ```sh
> uv add --dev watchfiles
> # or
> uv run uvicorn app.main:app --reload --reload-dir app
> ```
>
> Stop the dev server when you are done: `tmux kill-session -t kizuna`.

The API runs at `http://localhost:8000`.

Only Postgres is expected to run in Docker for the MVP local dev loop.

## Demo Seed

```sh
curl -X POST http://localhost:8000/api/demo/seed
```

## Checks

```sh
uv run pytest
uv run ruff check .
uv run mypy app tests
```
