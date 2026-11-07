"""Unix `compress` (.Z, LZW) decompression, as the 3.2 Installer does it.

The 3.2 floppies keep the Locale catalogs and help files, and the MMU
library guides, as `.Z` files. The Installer's UNCOMPRESS procedure copies
each with `(copyfiles ... (compression) (newname NAME))`, which writes the
decompressed file without its `.Z` suffix. The output is byte-identical to
`uncompress` (checked against a disk the Installer wrote).

The format is LZW with codes of 9 bits growing to the maximum in the header,
read least significant bit first. Codes come in groups of eight, so when the
code width grows, or a CLEAR code (256, in block mode) resets the table, the
rest of the current group is skipped. The width starts at 9 bits with room
for 512 codes even when the header allows only 9, so a 9-bit stream grows
to 10 bits once its table is full; `compress -b 9` writes it that way, and
gzip's decoder reads it that way. These quirks are why a plain LZW decoder
gets such files wrong.
"""

MAGIC = b"\x1f\x9d"
SUFFIX = ".Z"
INIT_BITS = 9
CLEAR = 256
BLOCK_MODE = 0x80
BITS_MASK = 0x1F


def is_compressed(data: bytes) -> bool:
    return data[:2] == MAGIC


def uncompressed_name(name: str) -> str | None:
    """The name the Installer gives a decompressed file, or None if not `.Z`."""
    if len(name) > len(SUFFIX) and name.endswith(SUFFIX):
        return name[: -len(SUFFIX)]
    return None


def uncompress(data: bytes) -> bytes:
    """Decompress `.Z` data. Raises ValueError for anything else."""
    if len(data) < 3 or not is_compressed(data):
        raise ValueError("not compress (.Z) data")
    max_bits = data[2] & BITS_MASK
    block_mode = bool(data[2] & BLOCK_MODE)
    if not INIT_BITS <= max_bits <= 16:
        raise ValueError(f"compress data with {max_bits}-bit codes is not supported")
    return _Decoder(data, max_bits, block_mode).run()


class _Decoder:
    def __init__(self, data: bytes, max_bits: int, block_mode: bool):
        self.data = data
        self.end = len(data) * 8
        self.max_bits = max_bits
        self.max_max_code = 1 << max_bits
        self.block_mode = block_mode
        self.pos = self.base = 3 * 8
        self._reset_table()

    def _reset_table(self) -> None:
        self.entries: list[bytes] = [bytes([i]) for i in range(256)]
        if self.block_mode:
            self.entries.append(b"")  # CLEAR holds no string
        self.n_bits = INIT_BITS
        self.max_code = (1 << INIT_BITS) - 1

    def _skip_to_group_end(self) -> None:
        group = self.n_bits * 8
        used = self.pos - self.base
        self.pos = self.base + -(-used // group) * group
        self.base = self.pos

    def _read(self) -> int | None:
        if self.pos + self.n_bits > self.end:
            return None
        first, offset = divmod(self.pos, 8)
        chunk = int.from_bytes(self.data[first : first + 4], "little")
        self.pos += self.n_bits
        return (chunk >> offset) & ((1 << self.n_bits) - 1)

    def run(self) -> bytes:
        out = bytearray()
        previous: bytes | None = None
        while True:
            if len(self.entries) > self.max_code:
                self._skip_to_group_end()
                self.n_bits += 1
                full = self.n_bits == self.max_bits
                self.max_code = self.max_max_code if full else (1 << self.n_bits) - 1
            code = self._read()
            if code is None:
                return bytes(out)
            if code == CLEAR and self.block_mode and previous is not None:
                self._skip_to_group_end()
                self._reset_table()
                previous = None
                continue
            if code < len(self.entries):
                current = self.entries[code]
            elif code == len(self.entries) and previous is not None:
                current = previous + previous[:1]
            else:
                raise ValueError("corrupt compress (.Z) data")
            out += current
            if previous is not None and len(self.entries) < self.max_max_code:
                self.entries.append(previous + current[:1])
            previous = current
