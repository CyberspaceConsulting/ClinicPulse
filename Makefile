.PHONY: export

export:
	uv export --locked --format requirements-txt --no-emit-project --output-file backend/requirements.txt
