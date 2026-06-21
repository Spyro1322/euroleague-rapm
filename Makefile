.PHONY: schema validate validate-quick ingest lint
schema:
	duckdb data/warehouse/warehouse.duckdb < sql/schema.sql
validate:          ## full Week-1 check, all seasons
	python scripts/validate_lineups.py --start 2007 --end 2025 --games-per-season 5
validate-quick:    ## smoke test, recent seasons
	python scripts/validate_lineups.py --start 2023 --end 2025 --games-per-season 3
lint:
	ruff check .
