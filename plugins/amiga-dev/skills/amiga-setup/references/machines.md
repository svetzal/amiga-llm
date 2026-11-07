# Stock machines in Amiberry

`model` in `amiga.toml` is an Amiberry quick-start model (`--model`). The
model sets CPU, chipset, memory and compatibility. Add `settings` only for
what differs on the user's real machine. Verified with Amiberry 8.5.0 on
macOS through `--dump-config`.

| Model | Defaults seen | Verified boot |
| --- | --- | --- |
| `A500` | 68000, OCS, `chipmem_size=1` (512 KB), `bogomem_size=2` (512 KB slow), cycle-exact | Kickstart 1.2 with Workbench 1.2: "890424 free memory" |
| `A3000` | 68030 and 68882, ECS, `chipmem_size=4` (2 MB), no fast RAM, cycle-exact | Kickstart 3.2 with `Install3.2.adf` and `a3000mem_size=8` |

Other models (`A500+`, `A600`, `A1000`, `A1200`, `A2000`, `A4000`, `CD32`,
`CDTV`) exist in `amiberry --help`; check their defaults with
`--dump-config` before relying on them.

## Settings that match common real machines

| Real machine fact | Setting |
| --- | --- |
| NTSC (North America, Japan) | `ntsc=true` |
| A500 with 1 MB chip RAM (ECS Agnus) | `chipmem_size=2`, `bogomem_size=0`, and `chipset=ecs_agnus` |
| A500 with 512 KB only | `bogomem_size=0` |
| A3000 motherboard fast RAM, in MB | `a3000mem_size=<n>` |
| Zorro II fast RAM, in MB | `fastmem_size=<n>` |

Only the A500 and A3000 rows have been booted. Treat the others as
starting points and confirm with `--dump-config` and a boot.

## Kickstart 1.x limits

These bite on any machine running Kickstart 1.2 or 1.3:

- Floppies must be OFS with the 1.x bootblock. `amiga-env adf` and
  `bootdisk` write that bootblock (xdftool `boot install boot1x`).
- Executables must use the 1.x hunk format: `vasm -kick1hunks`.
  `amiga-env asm` sets it.
- Only library functions up to V33 (1.2) or V34 (1.3) exist.
- A program can run by name from the root of the boot floppy; no `C:`
  directory is needed on the disk.
