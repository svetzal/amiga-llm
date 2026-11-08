# amiga-llm. Keep this file a thin index: each target is one line that calls
# a tool. Logic belongs in tools/amiga_env/, where it can be tested.

UV  ?= uv
ENV := $(UV) run --quiet amiga-env

.PHONY: help tools toolchain media media-verify doctor a500 a3000 a3500 a3000-dev system hello piano piano-disk guard test lint

SYSTEM ?= a3000-dev

help:
	@echo "make tools         install the latest Amiberry into .tools/"
	@echo "make toolchain     build the pinned vasm and vlink into .tools/"
	@echo "make media         copy licensed media in from the sources in .env (once)"
	@echo "make media-verify  check media/ against manifest.lock.json"
	@echo "make doctor        report what is installed and what is missing"
	@echo "make a500          boot the A500 to Workbench 1.2 (demos, games, hardware)"
	@echo "make a3000         boot the A3000 to Workbench 3.2 (desktop applications)"
	@echo "make a3500         boot the A3500 prototype to Workbench 2.04 (16 MB fast RAM)"
	@echo "make system        build runs/systems/$(SYSTEM) from systems/$(SYSTEM).toml"
	@echo "make a3000-dev     boot the A3000 development system (build it first)"
	@echo "make hello         assemble examples/hello into a boot disk, build/hello.adf"
	@echo "make piano         build EXP-004's Paula piano and render its pieces to runs/exp004"
	@echo "make piano-disk    put EXP-004's 68000 player and its pieces on build/piano/piano.adf"
	@echo "make guard         fail if git tracks licensed media or .env"
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

a3500:
	$(ENV) a3500

system:
	$(ENV) system build $(SYSTEM)

a3000-dev:
	$(ENV) a3000-dev

hello:
	$(ENV) bootdisk examples/hello/hello.s

piano:
	$(ENV) piano examples/piano/piano.toml

piano-disk:
	$(ENV) piano-disk examples/piano/piano.toml

guard:
	$(ENV) guard

lint:
	$(UV) run --quiet ruff format --check tools tests plugins
	$(UV) run --quiet ruff check tools tests plugins

test: lint
	$(UV) run --quiet pytest
