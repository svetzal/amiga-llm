"""Read the parts of an SFZ instrument that a Paula player needs.

Only these opcodes are read: sample, key, lokey, hikey, pitch_keycenter,
lovel, hivel, tune, volume, offset, trigger and ampeg_release, with
<control> default_path, the <global>, <master> and <group> headers they can
sit under, and the #define and #include directives. Everything else is
ignored. A region inherits from the headers above it, as in the SFZ format.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

HEADERS = ("control", "global", "master", "group", "region")
NOTE_NAMES = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
TOKEN = re.compile(r"<(\w+)>|([A-Za-z_][\w]*)=")
DEFINE = re.compile(r"^\s*#define\s+(\$\w+)\s+(.*?)\s*$")
INCLUDE = re.compile(r'^\s*#include\s+"([^"]+)"\s*$')


@dataclass(frozen=True)
class Region:
    sample: str
    lokey: int = 0
    hikey: int = 127
    pitch_keycenter: int = 60
    lovel: int = 1
    hivel: int = 127
    tune: int = 0  # cents
    volume: float = 0.0  # dB
    offset: int = 0  # samples skipped at the start
    trigger: str = "attack"
    ampeg_release: float = 0.001  # seconds

    def plays(self, key: int, velocity: int) -> bool:
        return self.lokey <= key <= self.hikey and self.lovel <= velocity <= self.hivel


INT_OPCODES = {"lokey", "hikey", "pitch_keycenter", "lovel", "hivel", "tune", "offset"}
KEY_OPCODES = {"lokey", "hikey", "pitch_keycenter"}
FLOAT_OPCODES = {"volume", "ampeg_release"}


def parse_key(value: str) -> int:
    """A MIDI note from a number or a name such as c4, c#4 or eb3 (c4 is 60)."""
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    match = re.fullmatch(r"([a-gA-G])([#b]?)(-?\d+)", value)
    if not match:
        raise ValueError(f"not a key: {value!r}")
    name, accidental, octave = match.groups()
    shift = {"#": 1, "b": -1, "": 0}[accidental]
    return (int(octave) + 1) * 12 + NOTE_NAMES[name.lower()] + shift


def expand(text: str, read: Callable[[str], str], defines: dict[str, str] | None = None) -> str:
    """The text with comments removed, #include files read in and $defines replaced."""
    defines = {} if defines is None else defines
    lines = []
    for line in re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL).splitlines():
        line = line.split("//", 1)[0]
        if match := DEFINE.match(line):
            defines[match[1]] = match[2]
            continue
        if match := INCLUDE.match(line):
            lines.append(expand(read(match[1]), read, defines))
            continue
        for name in sorted(defines, key=len, reverse=True):
            line = line.replace(name, defines[name])
        lines.append(line)
    return "\n".join(lines)


def parse(text: str, read: Callable[[str], str] = lambda name: "") -> list[Region]:
    """Every region in an SFZ file, with what it inherits applied.

    `read` returns the text of a file named by #include.
    """
    scopes: dict[str, dict[str, str]] = {h: {} for h in HEADERS}
    current: str | None = None
    regions: list[tuple[dict[str, str], dict[str, str], dict[str, str]]] = []
    for line in expand(text, read).splitlines():
        tokens = list(TOKEN.finditer(line))
        for index, token in enumerate(tokens):
            if token[1] is not None:
                header = token[1].lower()
                current = header if header in scopes else None
                if current is None:
                    continue  # a header this reader does not use; skip its opcodes
                for lower in HEADERS[HEADERS.index(current) :]:
                    scopes[lower] = {}
                if current == "region":
                    inherited = scopes["global"] | scopes["master"] | scopes["group"]
                    regions.append((dict(scopes["control"]), inherited, scopes["region"]))
                continue
            end = tokens[index + 1].start() if index + 1 < len(tokens) else len(line)
            if current is not None:
                scopes[current][token[2]] = line[token.end() : end].strip()
    return [_region(control, inherited | own) for control, inherited, own in regions]


def _region(control: dict[str, str], opcodes: dict[str, str]) -> Region:
    region = Region(sample="")
    for name, value in opcodes.items():
        if name == "sample":
            path = control.get("default_path", "") + value
            region = replace(region, sample=path.replace("\\", "/"))
        elif name == "key":
            key = parse_key(value)
            region = replace(region, lokey=key, hikey=key, pitch_keycenter=key)
        elif name in KEY_OPCODES:
            region = replace(region, **{name: parse_key(value)})
        elif name in INT_OPCODES:
            region = replace(region, **{name: int(value)})
        elif name in FLOAT_OPCODES:
            region = replace(region, **{name: float(value)})
        elif name == "trigger":
            region = replace(region, trigger=value)
    return region
