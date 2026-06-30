# fold@Scripps

## Development

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
uv sync                       # install dependencies
docker compose up -d postgres # start Postgres for tests/local runs
uv run pytest                 # run the test suite
uv run uvicorn fold_at_scripps.main:app --reload  # run the API locally
```

Or run the full stack in containers:

```bash
docker compose up --build
curl localhost:8000/health    # {"status":"ok"}
```
