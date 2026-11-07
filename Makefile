# amiga-llm. Keep this file a thin index: each target is one line that calls
# a tool. Logic belongs in tools/amiga_env/, where it can be tested.

UV  ?= uv
ENV := $(UV) run --quiet amiga-env

.PHONY: help tools media media-verify doctor test lint

help:
	@echo "make tools         install the latest Amiberry into .tools/"
	@echo "make media         copy licensed media in from the origin collection (once)"
	@echo "make media-verify  check media/ against manifest.lock.json"
	@echo "make doctor        report what is installed and what is missing"
	@echo "make test          lint and run the host-side tests"

tools:
	$(ENV) amiberry

media:
	$(ENV) media

media-verify:
	$(ENV) media-verify

doctor:
	$(ENV) doctor

lint:
	$(UV) run --quiet ruff format --check tools tests
	$(UV) run --quiet ruff check tools tests

test: lint
	$(UV) run --quiet pytest
