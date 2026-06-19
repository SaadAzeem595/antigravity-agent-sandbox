# Makefile for running ambient-expense-agent locally on ADK 2.0

.PHONY: install playground run generate-traces grade

install:
	uv sync

playground:
	agents-cli playground

run:
	uv run uvicorn expense_agent.fast_api_app:app --host 127.0.0.1 --port 8080

generate-traces:
	uv run python tests/eval/generate_traces.py

grade:
	agents-cli eval grade --traces artifacts/traces/generated_traces.json --config tests/eval/eval_config.yaml --output artifacts/grade_results/
