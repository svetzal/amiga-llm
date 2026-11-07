"""Run Amiberry's libretro core in this process, one emulated frame at a time.

Amiberry 8.5.0 has no audio/video recorder (its AVIOUTPUT code is not
compiled in) and its socket's FRAME_ADVANCE does not run a frame. The
release's libretro core is the same emulator as a library: each
`retro_run` emulates one frame, hands over that frame's picture, and hands
over the sound it made. A host that keeps every frame and every sample has a
recording in emulated time, whatever the host's own speed.

The core builds an Amiberry command line from its options (`--model`,
`-s ntsc=true`, `-r KICKSTART`, the content path) and calls Amiberry's own
main, so a machine is described by options, not by a .uae file.

`Core` is a gateway: a thin ctypes wrapper with no logic worth testing apart
from `option_default`. Only one core can be loaded in a process.
"""

import ctypes as C
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

# libretro.h
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_CONTENT_DIRECTORY = 30
ENV_GET_SAVE_DIRECTORY = 31
ENV_SET_SYSTEM_AV_INFO = 32
ENV_SET_GEOMETRY = 37
ENV_GET_CORE_OPTIONS_VERSION = 52
PIXEL_FORMAT_XRGB8888 = 1
MEMORY_SYSTEM_RAM = 2  # Amiberry's core: chip RAM, in the Amiga's (big-endian) byte order


def option_default(description: str) -> str:
    """An option's default from its libretro v0 description, `"Label; a|b|c"`: the first value."""
    _, _, values = description.partition("; ")
    if not values:
        raise ValueError(f"not a libretro option description: {description!r}")
    return values.split("|")[0]


class Frame(NamedTuple):
    pixels: bytes | None  # XRGB8888 rows, `pitch` bytes apart; None when the core repeated a frame
    width: int
    height: int
    pitch: int
    audio: bytes  # signed 16-bit little-endian stereo


class _Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_void_p)]


class _Geometry(C.Structure):
    _fields_ = [
        ("base_width", C.c_uint),
        ("base_height", C.c_uint),
        ("max_width", C.c_uint),
        ("max_height", C.c_uint),
        ("aspect_ratio", C.c_float),
    ]


class _Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class _AVInfo(C.Structure):
    _fields_ = [("geometry", _Geometry), ("timing", _Timing)]


class _GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p),
        ("data", C.c_void_p),
        ("size", C.c_size_t),
        ("meta", C.c_char_p),
    ]


_ENVIRONMENT = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
_VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
_SAMPLE = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
_BATCH = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
_POLL = C.CFUNCTYPE(None)
_INPUT = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Core:
    """Gateway: a libretro core loaded in this process, with no input attached.

    `options` answers the core's GET_VARIABLE; any option not given takes
    the default the core declared. The core's home (its amiberry.conf and
    folders) is `save_dir`; `system_dir` is where it looks for firmware.
    """

    def __init__(self, library: Path, options: Mapping[str, str], system_dir: Path, save_dir: Path):
        for folder in (system_dir, save_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self._strings: dict[str, C.Array] = {}
        self._options = dict(options)
        self._declared: dict[str, str] = {}
        self._dirs = {
            ENV_GET_SYSTEM_DIRECTORY: self._string("system", str(system_dir)),
            ENV_GET_CONTENT_DIRECTORY: self._string("system", str(system_dir)),
            ENV_GET_SAVE_DIRECTORY: self._string("save", str(save_dir)),
        }
        self.asked: set[str] = set()
        self.events: list[tuple] = []  # what the core announced: pixel format, timing, geometry
        self._pixels: bytes | None = None
        self._size = (0, 0, 0)
        self._audio = bytearray()
        self._callbacks = (
            _ENVIRONMENT(self._environment),
            _VIDEO(self._video),
            _SAMPLE(self._sample),
            _BATCH(self._batch),
            _POLL(lambda: None),
            _INPUT(lambda port, device, index, key: 0),
        )
        self._lib = C.CDLL(str(library))
        self._lib.retro_load_game.restype = C.c_bool
        self._lib.retro_get_memory_data.restype = C.c_void_p
        self._lib.retro_get_memory_size.restype = C.c_size_t
        setters = (
            "retro_set_environment",
            "retro_set_video_refresh",
            "retro_set_audio_sample",
            "retro_set_audio_sample_batch",
            "retro_set_input_poll",
            "retro_set_input_state",
        )
        for setter, callback in zip(setters, self._callbacks, strict=True):
            getattr(self._lib, setter)(callback)
        self._lib.retro_init()

    def load(self, content: Path) -> None:
        game = _GameInfo(str(content).encode(), None, 0, None)
        if not self._lib.retro_load_game(C.byref(game)):
            raise SystemExit(f"the libretro core could not load {content}")

    def timing(self) -> tuple[float, float]:
        """The core's own frames per second and sample rate."""
        info = _AVInfo()
        self._lib.retro_get_system_av_info(C.byref(info))
        return info.timing.fps, info.timing.sample_rate

    def run(self) -> Frame:
        """Emulate one frame; its picture and the sound handed over with it."""
        self._pixels = None
        self._audio.clear()
        self._lib.retro_run()
        width, height, pitch = self._size
        return Frame(self._pixels, width, height, pitch, bytes(self._audio))

    def read(self, address: int, size: int) -> bytes:
        """Bytes of chip RAM, as the Amiga sees them; empty before the machine runs."""
        base = self._lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        if not base or address + size > self._lib.retro_get_memory_size(MEMORY_SYSTEM_RAM):
            return b""
        return C.string_at(base + address, size)

    def close(self) -> None:
        self._lib.retro_unload_game()
        self._lib.retro_deinit()

    def _string(self, key: str, value: str) -> C.Array:
        self._strings[key] = C.create_string_buffer(value.encode())
        return self._strings[key]

    def _environment(self, command: int, data: int) -> bool:
        if command in self._dirs:
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(self._dirs[command])
            return True
        if command == ENV_SET_PIXEL_FORMAT:
            format_ = C.cast(data, C.POINTER(C.c_int))[0]
            self.events.append(("pixel_format", format_))
            return format_ == PIXEL_FORMAT_XRGB8888
        if command == ENV_GET_CORE_OPTIONS_VERSION:
            C.cast(data, C.POINTER(C.c_uint))[0] = 0  # declare options with SET_VARIABLES
            return True
        if command == ENV_SET_VARIABLES:
            self._declare(C.cast(data, C.POINTER(_Variable)))
            return True
        if command == ENV_GET_VARIABLE:
            return self._answer(C.cast(data, C.POINTER(_Variable))[0])
        if command == ENV_GET_VARIABLE_UPDATE:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if command == ENV_SET_SYSTEM_AV_INFO:
            info = C.cast(data, C.POINTER(_AVInfo))[0]
            self.events.append(("timing", info.timing.fps, info.timing.sample_rate))
            return True
        if command == ENV_SET_GEOMETRY:
            shape = C.cast(data, C.POINTER(_Geometry))[0]
            self.events.append(("geometry", shape.base_width, shape.base_height))
            return True
        return False

    def _declare(self, variables) -> None:
        index = 0
        while variables[index].key:
            key = variables[index].key.decode()
            description = C.cast(variables[index].value, C.c_char_p).value.decode()
            self._declared[key] = option_default(description)
            index += 1

    def _answer(self, variable: _Variable) -> bool:
        key = variable.key.decode()
        self.asked.add(key)
        value = self._options.get(key, self._declared.get(key))
        if value is None:
            return False
        variable.value = C.addressof(self._string(f"option:{key}", value))
        return True

    def _video(self, data: int, width: int, height: int, pitch: int) -> None:
        if data:
            self._pixels = C.string_at(data, pitch * height)
            self._size = (width, height, pitch)

    def _sample(self, left: int, right: int) -> None:
        self._audio += left.to_bytes(2, "little", signed=True) + right.to_bytes(
            2, "little", signed=True
        )

    def _batch(self, data, frames: int) -> int:
        self._audio += C.string_at(data, frames * 4)
        return frames
