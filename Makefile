# amiga-llm. Keep this file a thin index: each target is one line that calls
# a tool. Logic belongs in tools/amiga_env/, where it can be tested.

UV  ?= uv
ENV := $(UV) run --quiet amiga-env

.PHONY: help tools toolchain media media-verify doctor a500 a3000 hello test lint

help:
	@echo "make tools         install the latest Amiberry into .tools/"
	@echo "make toolchain     build the pinned vasm and vlink into .tools/"
	@echo "make media         copy licensed media in from the origin collection (once)"
	@echo "make media-verify  check media/ against manifest.lock.json"
	@echo "make doctor        report what is installed and what is missing"
	@echo "make a500          boot the A500 to Workbench 1.2 (demos, games, hardware)"
	@echo "make a3000         boot the A3000 to Workbench 3.2 (desktop applications)"
	@echo "make hello         assemble examples/hello into a boot disk, build/hello.adf"
	@echo "make test          lint and run the host-side tests"

tools:
	$(ENV) amiberry

toolchain:
	$(ENV) toolchain

media:
	$(ENV) media

media-verify:
	$(ENV) media-verify

doctor:
	$(ENV) doctor

a500:
	$(ENV) a500

a3000:
	$(ENV) a3000

hello:
	$(ENV) bootdisk examples/hello/hello.s

lint:
	$(UV) run --quiet ruff format --check tools tests plugins
	$(UV) run --quiet ruff check tools tests plugins

test: lint
	$(UV) run --quiet pytest
