.PHONY: help postgres build-frontend migrate

help:  ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

postgres:  ## Start the Postgres container
	docker compose up -d postgres

build-frontend:  ## Build the SPA into frontend/dist (host needs no Node)
	rm -rf frontend/dist
	docker build --target dist --output type=local,dest=frontend/dist .

migrate:  ## Apply DB migrations
	uv run alembic upgrade head
