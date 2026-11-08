"""Drive the A3500 piano's screen on the emulated A3500, as a person would, and check it.

The volume boots the test build (LOG=1) with no arguments: the screen. The
run touches nothing until the rotation starts piece 1, then plays through
EXP-004's checks: the rotation's gap, a click on a line while a piece plays,
F (the filter) twice, a piece's key, Space, a quiet that must stay quiet,
and Q. Warp is on only between the steps; every key, click and screenshot
happens with it off. Every time is the player's own (vertical blanks), so
warp changes none of them.

Each piece the player ends leaves logs/NAME.log and logs/NAME.stat on the
volume. A piece that played to its end must match the model's log byte for
byte; a piece cut short must match the model's first blocks. Screenshots
are checked for the picture (against title.ilbm itself), the gold line
and the scopes.
"""

import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

import numpy as np

from .. import profile, session
from . import build3500, disk, picture, player3500, run3500
from . import font as font_mod
from . import screen as screen_mod

WINDOW_MOUSE_Y, WINDOW_MOUSE_X = 12, 14
SPACE, F_KEY, Q_KEY = 0x40, 0x23, 0x10
CIAA_PRA = 0xBFE001
LED_BIT = 1
WAITING, PLAYING = 3, 1
SCALE = 2  # Amiberry's screenshot: each lowres pixel is 2 x 2


class Origin(NamedTuple):
    x: int
    y: int
    difference: float  # mean absolute difference from the picture, 0 to 255


def find_origin(shot: np.ndarray, preview: np.ndarray, xs: range, ys: range) -> Origin:
    """Where the 320x200 screen sits in a screenshot: the offset at which the
    picture, doubled, differs least from it (the list and the floor
    band, which the scopes and the gold line do not change, are left in)."""
    big = preview.repeat(SCALE, axis=0).repeat(SCALE, axis=1).astype(int)
    best = None
    for y in ys:
        for x in xs:
            window = shot[y : y + big.shape[0], x : x + big.shape[1]].astype(int)
            if window.shape != big.shape:
                continue
            difference = float(np.abs(window - big).mean())
            if best is None or difference < best.difference:
                best = Origin(x, y, difference)
    if best is None:
        raise SystemExit("the screenshot is smaller than the screen")
    return best


def colour_rows(shot: np.ndarray, origin: Origin, rgb: tuple[int, int, int], box) -> int:
    """Pixels of a colour inside a box of screen pixels (left, top, right, bottom)."""
    left, top, right, bottom = box
    area = shot[
        origin.y + SCALE * top : origin.y + SCALE * bottom,
        origin.x + SCALE * left : origin.x + SCALE * right,
    ].astype(int)
    return int((np.abs(area - np.array(rgb)).sum(axis=2) < 30).sum())


def gold_lines(shot: np.ndarray, origin: Origin, recipe: build3500.Recipe) -> list[int]:
    """The list's lines that show the gold of the highlight."""
    spec = recipe.screen
    gold = picture.rgb_of(picture.parse_ocs(spec.highlight))
    found = []
    for index, top in enumerate(line_tops(recipe)):
        box = (spec.list_box.left, top, spec.list_box.right, top + spec.line_pitch - 2)
        if colour_rows(shot, origin, gold, box) > 20:
            found.append(index)
    return found


def line_tops(recipe: build3500.Recipe) -> list[int]:
    """Each piece's line's first row on the screen."""
    from .. import project

    spec = recipe.screen
    font = font_mod.load(project.root() / spec.font)
    return [line.top for line in screen_mod.layout(disk.titles(recipe), spec, font).pieces]


def scope_columns(shot: np.ndarray, origin: Origin, recipe: build3500.Recipe) -> list[float]:
    """For each of the two scopes (the left channel's, then the right's), the share
    of its columns with a trace pixel in the band. Both draw in the mix trace colour."""
    spec, scopes = recipe.screen, recipe.scopes
    if scopes is None:
        raise SystemExit("the recipe has no [scopes] table")
    band = (spec.scope_band.top, spec.scope_band.bottom)
    rgb = np.array(picture.rgb_of(picture.parse_ocs(spec.mix_trace)))
    rows = shot[origin.y + SCALE * band[0] : origin.y + SCALE * band[1]].astype(int)
    shares = []
    for left in scopes.left:
        columns = [origin.x + SCALE * x for x in range(left, left + scopes.width)]
        near = np.abs(rows[:, columns] - rgb).sum(axis=2) < 30
        shares.append(round(float(near.any(axis=0).mean()), 2))
    return shares


def compare_prefix(model: bytes, machine: bytes) -> dict:
    """A log cut short against the model's: the same header but for the block count,
    and the same blocks as far as it goes."""
    header = player3500.LOG_HEADER_BYTES
    blocks = (len(machine) - header) // player3500.LOG_BLOCK_BYTES
    same_header = machine[: header - 4] == model[: header - 4]
    same = machine[header:] == model[header : len(machine)]
    return {"machine_blocks": blocks, "same_header": same_header, "same_blocks": same}


def latency(status: run3500.Status) -> dict:
    """Milliseconds from the task taking a choice to each step, in vertical blanks."""
    hz = status.vblank_hz or 60
    steps = {
        "line_gold": status.gold_at,
        "first_block_made": status.playing_at,
        "first_note": status.first_note_at,
    }
    return {
        f"{name}_ms": round((at - status.chosen_at) * 1000 / hz)
        for name, at in steps.items()
        if at >= status.chosen_at
    }


STEER_LIMIT = 40  # the largest SEND_MOUSE count sent at once


def steer_move(
    at: tuple[int, int], target: tuple[int, int], gain: Sequence[float]
) -> tuple[int, int] | None:
    """The next SEND_MOUSE move towards target, or None within a pixel of it: most
    of the way at the learnt gain, at least one count on an axis still off."""
    move = []
    for axis in (0, 1):
        distance = target[axis] - at[axis]
        if abs(distance) <= 1:
            move.append(0)
            continue
        count = round(distance * gain[axis] * 0.7)
        if count == 0:
            count = 1 if distance > 0 else -1
        move.append(max(-STEER_LIMIT, min(STEER_LIMIT, count)))
    return None if move == [0, 0] else (move[0], move[1])


def learn_gain(
    gain: Sequence[float], move: tuple[int, int], before: tuple[int, int], after: tuple[int, int]
) -> list[float]:
    """Counts per pixel on each axis, from a move and where the pointer went."""
    learnt = list(gain)
    for axis in (0, 1):
        moved = after[axis] - before[axis]
        if move[axis] and moved and (moved > 0) == (move[axis] > 0):
            learnt[axis] = max(0.5, min(20.0, abs(move[axis] / moved)))
    return learnt


class Screen:
    """Gateway: the emulator this run started, its screen and its mouse."""

    def __init__(self, machine: run3500.Machine, out: Path):
        self.machine, self.out = machine, out

    def send(self, *fields: str) -> list[str]:
        return self.machine._emulator.send(*fields)

    def status(self) -> run3500.Status:
        return self.machine.status()

    def read(self, address: int, size: int) -> int:
        reply = self.send("READ_MEM", hex(address), str(size))
        if reply[0] != "OK":
            raise SystemExit(f"READ_MEM {address:#x} failed: {' '.join(reply)}")
        return int(reply[1])

    def press(self, code: int) -> None:
        for state in ("1", "0"):
            self.send("SEND_KEY", str(code), state)
            time.sleep(0.1)

    def pointer(self, window: int) -> tuple[int, int]:
        return self.read(window + WINDOW_MOUSE_X, 2), self.read(window + WINDOW_MOUSE_Y, 2)

    def click(self, window: int, target: tuple[int, int], tries: int = 120) -> tuple[int, int]:
        """Steer the pointer to `target` and press the left button. SEND_MOUSE is
        relative and Intuition scales it, so the gain on each axis is learnt from
        how far each move went (steer_move)."""
        gain = [4.0, 4.0]
        for _ in range(tries):
            at = self.pointer(window)
            move = steer_move(at, target, gain)
            if move is None:
                break
            self.send("SEND_MOUSE", str(move[0]), str(move[1]), "0")
            time.sleep(0.15)
            gain = learn_gain(gain, move, at, self.pointer(window))
        else:
            raise SystemExit(f"the pointer did not reach {target}; it is at {at}")
        self.send("SEND_MOUSE", "0", "0", "1")
        time.sleep(0.1)
        self.send("SEND_MOUSE", "0", "0", "0")
        return at

    def shot(self, name: str) -> np.ndarray:
        from PIL import Image

        path = self.out / f"screen-{name}.png"
        self.send("SCREENSHOT", str(path.resolve()))
        return np.asarray(Image.open(path).convert("RGB"))

    def warp(self, on: bool) -> None:
        self.machine.warp(on)

    def wait(self, ready: Callable[[run3500.Status], bool], timeout: float) -> run3500.Status:
        deadline = time.monotonic() + timeout
        while True:
            status = self.status()
            if status.magic == run3500.MAGIC and ready(status):
                return status
            if status.state == run3500.FAILED:
                raise SystemExit(f"the player failed: {status}")
            if time.monotonic() > deadline:
                raise SystemExit(f"not there within {timeout:g} s: {status}")
            time.sleep(0.25)


def run(machine: profile.Machine, recipe: build3500.Recipe, out: Path) -> dict:
    """The screen's whole scenario; see the module notes. Writes `<out>/screen-run.json`."""
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    volume = out / "volume"
    piano = build3500.make_piano(recipe)
    names = [p.name for p in recipe.pieces]
    models = run3500.model_logs(recipe, piano, [names[0], names[1], names[2], names[-1]])
    run3500.write_files(recipe, piano, volume, "player\n", log=True)
    preview = screen_pixels(volume / run3500.PICTURE)
    args = [
        *profile.base_args(machine),
        *session.volume_args([session.Volume("DH0", run3500.VOLUME_LABEL, volume, 0)]),
    ]
    amiga = run3500.Machine(args, out / "screen-run.amiberry.log")
    screen = Screen(amiga, out)
    found: dict = {"steps": {}}
    began = time.monotonic()
    try:
        amiga.connect(volume)
        _scenario(screen, recipe, names, models, preview, volume, found["steps"])
    finally:
        amiga.stop()
    found["wall_seconds"] = round(time.monotonic() - began, 1)
    (out / "screen-run.json").write_text(json.dumps(found, indent=2) + "\n")
    return found


def screen_pixels(ilbm: Path) -> np.ndarray:
    """The 320x200 screen the player shows, as RGB pixels, from its title.ilbm."""
    indices, colours = picture.read_ilbm(ilbm.read_bytes())
    lookup = np.array([picture.rgb_of(w) for w in colours], dtype=np.uint8)
    return lookup[indices]


def piece_report(volume: Path, name: str, model: bytes | None) -> dict:
    """A finished or stopped piece's status file and log, against the model's."""
    stat = volume / "logs" / f"{name}.stat"
    status = run3500.parse_status(stat.read_bytes())
    log = (volume / "logs" / f"{name}.log").read_bytes()
    found: dict = {
        "stopped": bool(status.stopped),
        "cpu": run3500.cpu_report(status),
        "worst_total_percent": round(100 * status.worst_total_e / run3500.BLOCK_E, 1),
        "screen_percent": round(100 * status.task_e / max(status.blocks, 1) / run3500.BLOCK_E, 2),
        "units_drawn": status.units,
        "worst_unit_e": status.unit_max_e,
    }
    if model is not None:
        found["log"] = (
            compare_prefix(model, log) if status.stopped else run3500.compare_logs(model, log)
        )
    return found


def _wait_stat(volume: Path, name: str, timeout: float) -> None:
    stat = volume / "logs" / f"{name}.stat"
    deadline = time.monotonic() + timeout
    while not (stat.exists() and stat.stat().st_size == run3500.STATUS_BYTES):
        if time.monotonic() > deadline:
            raise SystemExit(f"no status file for {name} within {timeout:g} s")
        time.sleep(0.5)


def _scenario(
    screen: Screen,
    recipe: build3500.Recipe,
    names: Sequence[str],
    models: dict[str, bytes],
    preview: np.ndarray,
    volume: Path,
    steps: dict,
) -> None:
    hz = 60
    idle = screen.wait(lambda s: s.state == WAITING and s.screen_at > 0, 120)
    hz = idle.vblank_hz or 60
    shot = screen.shot("idle")
    origin = find_origin(shot, preview, range(40, 120, 2), range(20, 80, 2))
    steps["start"] = {
        "samples_loaded_s": round(idle.loaded_at / hz, 2),
        "scores_loaded_frames": idle.preload_frames,
        "screen_up_s": round(idle.screen_at / hz, 2),
        "screenshot_origin": origin._asdict(),
        "gold_lines_idle": gold_lines(shot, origin, recipe),
    }

    # 1. Touch nothing: the rotation plays piece 1.
    first = screen.wait(lambda s: s.starts >= 1, 60)
    time.sleep(3)
    shot = screen.shot("piece-1-by-itself")
    steps["first_by_itself"] = {
        "piece": names[first.piece],
        "rotated": first.rotated,
        "emulated_s_from_screen_to_choice": round((first.chosen_at - first.screen_at) / hz, 2),
        "latency": latency(first),
        "gold_lines": gold_lines(shot, origin, recipe),
        "scopes": scope_columns(shot, origin, recipe),
    }

    # 2. To its end in warp; its log whole.
    screen.warp(True)
    _wait_stat(volume, names[0], 900)
    ended = screen.wait(lambda s: s.played >= 1, 60)
    screen.warp(False)
    steps["first_piece"] = piece_report(volume, names[0], models[names[0]])

    # 3. The gap, then piece 2 by the rotation.
    screen.warp(True)
    second = screen.wait(lambda s: s.starts >= 2, 120)
    screen.warp(False)
    steps["second_by_rotation"] = {
        "piece": names[second.piece],
        "rotated": second.rotated,
        "gap_s": round((second.chosen_at - ended.ended_at) / hz, 2),
        "latency": latency(second),
    }

    # 4. 20 s into it, a click on the last line.
    screen.warp(True)
    screen.wait(lambda s: s.blocks >= 20 * 55, 300)
    screen.warp(False)
    before = screen.status()
    target = disk.click_points(recipe)[names[-1]]
    clicked_at = screen.click(before.window, target)
    clicked = screen.wait(lambda s: s.starts > before.starts, 30)
    time.sleep(2)
    shot = screen.shot("clicked-last")
    _wait_stat(volume, names[1], 30)
    steps["click_mid_piece"] = {
        "clicked_at": clicked_at,
        "piece": names[clicked.piece],
        "latency": latency(clicked),
        "gold_lines": gold_lines(shot, origin, recipe),
        "scopes": scope_columns(shot, origin, recipe),
        "stopped_piece": piece_report(volume, names[1], models[names[1]]),
    }

    # 5. F twice: the filter bit, and back.
    states = [screen.read(CIAA_PRA, 1)]
    for _ in range(2):
        screen.press(F_KEY)
        time.sleep(1)
        states.append(screen.read(CIAA_PRA, 1))
    steps["filter"] = {
        "led_bit_before_after_after": [(s >> LED_BIT) & 1 for s in states],
        "presses_counted": screen.status().filter_keys,
    }

    # 6. Key 3: the third piece, switching from the last.
    before = screen.status()
    screen.press(disk.RAW_KEYS[disk.MENU_KEYS[2]])
    keyed = screen.wait(lambda s: s.starts > before.starts, 30)
    _wait_stat(volume, names[-1], 30)
    steps["key_3"] = {
        "piece": names[keyed.piece],
        "latency": latency(keyed),
        "stopped_piece": piece_report(volume, names[-1], models[names[-1]]),
    }

    # 7. To its end in warp; its log whole.
    screen.warp(True)
    _wait_stat(volume, names[2], 600)
    third_end = screen.wait(lambda s: s.played > keyed.played, 60)
    screen.warp(False)
    steps["third_piece"] = piece_report(volume, names[2], models[names[2]])

    # 8. The next by the rotation; Space 5 s in; 30 s of quiet.
    screen.warp(True)
    nxt = screen.wait(lambda s: s.starts > third_end.starts, 120)
    screen.wait(lambda s: s.blocks >= 5 * 55, 60)
    screen.warp(False)
    screen.press(SPACE)
    held = screen.wait(lambda s: s.state == WAITING and s.played > nxt.played, 30)
    time.sleep(1)
    shot = screen.shot("space")
    screen.warp(True)
    quiet = screen.wait(lambda s: s.vblanks >= held.vblanks + 30 * hz, 120)
    screen.warp(False)
    steps["space"] = {
        "piece_stopped": names[nxt.piece],
        "rotation_held": held.rotate_at == 0xFFFFFFFF,
        "gold_lines": gold_lines(shot, origin, recipe),
        "starts_in_30_quiet_s": quiet.starts - held.starts,
    }

    # 9. Q.
    screen.press(Q_KEY)
    done = screen.wait(lambda s: s.state == 2, 30)
    steps["quit"] = {
        "ended": done.state == 2,
        "led_bit_after": (screen.read(CIAA_PRA, 1) >> LED_BIT) & 1,
    }
