# A thin index over amiga-env: each target is one line that calls it.
# Boot a machine defined in amiga.toml with `amiga-env <machine> [DISK.adf]`.

AMIGA_ENV ?= amiga-env

.PHONY: help tools toolchain media media-verify doctor hello guard

help:
	@echo "make tools         install the latest Amiberry into .tools/"
	@echo "make toolchain     build the pinned vasm and vlink into .tools/"
	@echo "make media         copy licensed media in from the sources in .env (once)"
	@echo "make media-verify  check media/ against manifest.lock.json"
	@echo "make doctor        report what is installed and what is missing"
	@echo "make hello         assemble examples/hello into a boot disk, build/hello.adf"
	@echo "make guard         fail if git tracks licensed media or .env"
	@echo "amiga-env <machine> [DISK.adf]   boot a machine from amiga.toml"

tools:
	$(AMIGA_ENV) amiberry

toolchain:
	$(AMIGA_ENV) toolchain

media:
	$(AMIGA_ENV) media

media-verify:
	$(AMIGA_ENV) media-verify

doctor:
	$(AMIGA_ENV) doctor

hello:
	$(AMIGA_ENV) bootdisk examples/hello/hello.s

guard:
	$(AMIGA_ENV) guard
