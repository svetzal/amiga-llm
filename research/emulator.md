# Amiberry as the machine-level emulator

Amiberry (BlitterStudio, a WinUAE-derived emulator) is the whole-machine
emulator for this project. This note records what is verified about it and
what is still a hypothesis.

## Installation (verified 2026-11-07)

`make tools` asks the GitHub API for the latest release of
`BlitterStudio/amiberry`, downloads the asset for this host, and checks it
against the release's `SHA256SUMS` before unpacking. Each version gets its own
directory under `.tools/amiberry/`; `.tools/amiberry/current` links to the one
in use. `amiga-env amiberry --tag vX.Y.Z` installs a specific release, which
is how to roll back.

| Host | Asset |
| --- | --- |
| macOS (Apple silicon or Intel) | `Amiberry-<v>-macOS-universal.dmg` |
| Linux x86_64 (mojility-ops-01) | `Amiberry-<v>-x86_64.AppImage` |
| Linux aarch64 | `Amiberry-<v>-aarch64.AppImage` |

On 2026-11-07 the latest release was v8.5.0 (published 2026-10-27). The copy
in `/Applications` on the Mac was 8.3.0, and nothing here uses it.

The Linux path is written but not yet run.

## Isolation (verified 2026-11-07 on macOS)

Amiberry reads `~/Library/Application Support/Amiberry/amiberry.conf` on
macOS. On the Mac that global file sets `base_content_path` and `rom_path`
inside the OneDrive "Amiga Retro" folder, so an unmodified run reads ROMs and
writes save states there.

Two ways to stop that were tried:

1. **Portable mode.** Amiberry enters portable mode when an
   `amiberry.portable` marker sits beside its executable, which on macOS is
   `Amiberry.app/Contents/MacOS/`. macOS refuses the write ("Operation not
   permitted") because the bundle is protected, and modifying a signed bundle
   would break its signature in any case. Rejected.
2. **A private HOME.** Running Amiberry with `HOME=<project>/runs/home` moves
   the settings directory, content directory, ROM path, configurations, save
   states and screenshots under the project. `amiga-env run` does this. Before
   each run it sets the path keys in that `amiberry.conf` (`rom_path` is
   `media/rom/`) and keeps the settings Amiberry saved there. Adopted.

`make doctor` runs `amiberry --dump-paths` under the private HOME and fails if
any resolved path is outside the project. The one exception is
`compiled_data_dir`, a compiled-in fallback that the macOS build does not use
because its data directory is inside the bundle.

`AMIBERRY_HOME_DIR` exists in the binary but did not override the global
settings file when tried.

## Command-line surface useful for automation

From `amiberry --help` (v8.5.0):

| Option | Use here |
| --- | --- |
| `-f <file>` | load a `.uae` configuration the tools generate |
| `-G` | start emulation with no GUI |
| `-s key=value` | set any configuration option directly |
| `-m VOL:path` | mount a host directory as an Amiga volume |
| `-0` to `-3 <adf>` | insert floppy images |
| `-r` / `-K` | main and extended Kickstart ROM |
| `-w 0` / `-w -1` | cycle-exact CPU or maximum speed |
| `--statefile` | start from a save state |
| `--dump-paths` | print every resolved path and exit |
| `--log` | log to the console |

## Hypotheses to test

These are the questions the first experiments answer. None is established.

- A host directory mounted with `-m` gives the host and the Amiga a shared
  folder that an agent can write a program into and read results back from,
  without driving the GUI.
- The emulated serial port can be bridged to a TCP socket on the host, giving
  a text console the agent can read and write.
- Amiberry can produce screenshots on demand without the window-finding and
  retry logic coco-llm needed for XRoar.
- The release also ships a libretro core
  (`amiberry-libretro-macOS-arm64.dylib`). A small libretro host could step
  frames, inject keys and read the frame buffer directly. That would make
  observation deterministic. It is a larger build, so it waits until the
  simpler routes above are measured.
- Amiberry runs headless on mojility-ops-01 from the AppImage, so long runs
  can move off the Mac.
