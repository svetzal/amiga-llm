# Where licensed Amiga media comes from

Copy only from a collection the user owns. File names below are as found in
one real collection (Amiga Forever 10 Plus and the AmigaOS 3.2 CD, checked
2026-11-07). Other editions may name or place files differently, so confirm
by listing the folder, not by assuming.

Each distribution is a source in the project's manifest, located through a
variable in `.env`. Item paths are relative to the folder the variable names.

| Source | Variable | Points at |
| --- | --- | --- |
| `amiga_forever` | `AMIGA_FOREVER_DIR` | The `Amiga Files` folder (holds `Shared/rom` and `Shared/adf`) |
| `amigaos32` | `AMIGAOS32_DIR` | The root of the 3.2 CD or download (holds `ROM/`, `ADF/`, `NDK3.2/`) |
| `collection` | `AMIGA_COLLECTION_DIR` | Any personal folder of manuals or configurations |

## Amiga Forever (Cloanto)

Files are under `Shared/` in the `Amiga Files` folder. On Windows that folder
is usually under the public Documents folder; on a Mac it is wherever the
user copied it.

| Folder | Contents |
| --- | --- |
| `rom/` | Kickstart ROMs named `amiga-os-<version>[-<model>].rom`, plus `rom.key` |
| `adf/` | Workbench floppies named `amiga-os-<version>-<disk>.adf` |

ROMs from 1.2 up, by name (version digits without dots):

| Release | Files |
| --- | --- |
| 1.2 | `amiga-os-120.rom` |
| 1.3 | `amiga-os-130.rom` (A500 and A2000), `amiga-os-130-a3000.rom` |
| 1.4 (A3000 beta) | `amiga-os-140-a3000.rom` |
| 2.04 | `amiga-os-204.rom`, `amiga-os-204-a3000.rom` |
| 2.05 | `amiga-os-205-a600.rom` |
| 3.0 | `amiga-os-300-a1200.rom`, `amiga-os-300-a4000.rom` |
| 3.1 | `amiga-os-310-<a600, a1200, a3000, a4000, a4000t, cd32>.rom` |
| 3.x | `amiga-os-3x0-<model>.rom` |
| Extension ROMs | `amiga-os-130-a570-ext.rom`, `amiga-os-130-cdtv-ext.rom`, `amiga-os-230-cdtv-ext.rom`, `amiga-os-310-cd32-ext.rom` (load with `-K`) |

Older ROMs (`amiga-os-070`, `100`, `110`, `120`) and non-Kickstart ROMs
(`amiga-boot-*`, `amiga-bonus-*`, AROS, third-party boards) are also there.

**The ROMs are encrypted.** Each starts with the text `AMIROMTYPE1`.
Amiberry decrypts them only when `rom.key` from the same installation sits
in the same folder. Always add `rom.key` to the manifest beside them.

Workbench floppies: `amiga-os-<version>-workbench.adf` for 1.0 to 3.1, and
for 2.04 and later also `-extras`, `-fonts`, `-install`, `-locale` and
(3.0, 3.1) `-storage`. Note that 1.3 is `amiga-os-134-*` (Workbench 1.3.4).
Each release's Workbench floppy boots on its own Kickstart (verified for 1.2).

## AmigaOS 3.2 (Hyperion)

From the 3.2 CD or download:

| Folder | Contents |
| --- | --- |
| `ROM/` | `kickCDTVa1000a500a2000a600.rom`, `kicka1200.rom`, `kicka3000.rom`, `kicka4000.rom`, `kicka4000t.rom`, `CDTV-Extended-ROM.rom`. Not encrypted. |
| `ADF/` | `Install3.2.adf`, `Workbench3.2.adf`, `Extras3.2.adf`, `Classes3.2.adf`, `Fonts.adf`, `Storage3.2.adf`, `Locale.adf`, `Locale-EN.adf`, `HDSetup3.2.adf`, `MMULibs.adf`, `ModulesA500_3.2.adf` and the other `Modules*` disks |
| `NDK3.2/` | The developer kit: `Include_H`, `Include_I`, `FD`, `SFD`, `Autodocs`, `lib`, `Examples` |

On a 3.2 Kickstart, `Install3.2.adf` boots to a Workbench screen and
`Workbench3.2.adf` alone stops at the insert-disk screen (verified on an
A3000 profile). A full 3.2 system belongs on a hard-drive image.

## Developer headers per OS release

The NDK 3.2 FD files mark when each function arrived ("functions in V33 or
higher (Release 1.2)", V36 for 2.0, V39 for 3.0), which is enough to know
which library calls a given Kickstart has. Structure layouts for older
releases need that release's own headers, which shipped with the compilers
and assemblers of the time. Ask the user what they own before adding any.
