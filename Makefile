# amiga-llm. Keep this file a thin index: each target is one line that calls
# a tool. Logic belongs in tools/amiga_env/, where it can be tested.

UV  ?= uv
ENV := $(UV) run --quiet amiga-env

.PHONY: help tools toolchain media media-verify doctor a500 a3000 a3500 a3000-dev system hello mixbench piano piano3500 piano3500-run piano3500-image piano3500-16k piano3500-16k-image piano3500-16k-video piano-disk piano-video piano3500-video guard test lint

SYSTEM ?= a3000-dev
PIECES ?= nocturne-op9-2 bwv846
# For the videos, all optional: SECONDS=40 (a test run), STEPS=master,measure, OUT=runs/x
VIDEO = $(if $(SECONDS),--seconds $(SECONDS)) $(if $(STEPS),--steps $(STEPS)) $(if $(OUT),--out $(OUT))

help:
	@echo "make tools         install the latest Amiberry into .tools/"
	@echo "make toolchain     build the pinned vasm and vlink into .tools/"
	@echo "make media         copy licensed media in from the sources in .env (once)"
	@echo "make media-verify  check media/ against manifest.lock.json"
	@echo "make doctor        report what is installed and what is missing"
	@echo "make a500          boot the A500 to Workbench 1.2 (demos, games, hardware)"
	@echo "make a3000         boot the A3000 to Workbench 3.2 (desktop applications)"
	@echo "make a3500         boot the A3500 prototype to Workbench 2.1 (16 MB fast RAM)"
	@echo "make system        build runs/systems/$(SYSTEM) from systems/$(SYSTEM).toml"
	@echo "make a3000-dev     boot the A3000 development system (build it first)"
	@echo "make hello         assemble examples/hello into a boot disk, build/hello.adf"
	@echo "make mixbench      EXP-005's 68030 mixing timing test, build/mixbench.adf (A3500)"
	@echo "make piano         build EXP-004's Paula piano and render its pieces to runs/exp004"
	@echo "make piano3500     model EXP-006's A3500 piano (16 mixed voices) and render to runs/exp006"
	@echo "make piano3500-run play PIECES with EXP-006's 68030 player on the A3500, check its logs"
	@echo "make piano3500-image  the A3500 piano's BlueSCSI image, build/piano3500/piano3500.hdf"
	@echo "make piano-disk    put EXP-004's 68000 player and its pieces on build/piano/piano.adf"
	@echo "make piano-video   record the A500 floppy playing by itself; master in runs/video"
	@echo "make piano3500-video  record the A3500 image playing by itself; master in runs/video3500"
	@echo "make piano3500-16k, piano3500-16k-image, piano3500-16k-video"
	@echo "                   the same for the 16 kHz edition: runs/exp006-16k,"
	@echo "                   build/piano3500-16k/piano3500.hdf, runs/video3500-16k"
	@echo "                   (the videos take SECONDS=, STEPS= and OUT=)"
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

mixbench:
	$(ENV) bootdisk examples/mixbench/mixbench.s

piano:
	$(ENV) piano examples/piano/piano.toml

piano3500:
	$(ENV) piano3500 examples/piano3500/piano.toml

piano3500-run:
	$(ENV) piano3500-run examples/piano3500/piano.toml $(PIECES)

piano3500-image:
	$(ENV) piano3500-image examples/piano3500/piano.toml --boot

piano-disk:
	$(ENV) piano-disk examples/piano/piano.toml

piano-video:
	$(ENV) piano-video examples/piano/piano.toml $(VIDEO)

piano3500-video:
	$(ENV) piano3500-video examples/piano3500/piano.toml $(VIDEO)

piano3500-16k:
	$(ENV) piano3500 examples/piano3500-16k/piano.toml

piano3500-16k-image:
	$(ENV) piano3500-image examples/piano3500-16k/piano.toml --boot

piano3500-16k-video:
	$(ENV) piano3500-video examples/piano3500-16k/piano.toml --out runs/video3500-16k $(VIDEO)

guard:
	$(ENV) guard

lint:
	$(UV) run --quiet ruff format --check tools tests plugins
	$(UV) run --quiet ruff check tools tests plugins

test: lint
	$(UV) run --quiet pytest
