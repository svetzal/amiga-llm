"""Build the A3500 piano (EXP-006) from a recipe: samples, voice logs, WAVs, a report.

A recipe (TOML) names the SFZ piano under media/, the pieces (its own
[[piece]] tables, or `pieces`, another recipe whose [[piece]] tables to
use), the sample choices (samples.SampleSpec), the number of velocity
layers, the volume of the loudest sample at velocity 127, the pan width and
the fast RAM budget for the samples. Everything goes to the recipe's `out`
folder under the project.

Files written:

- `samples.bin`: every sample end to end, signed 16-bit big-endian, layer
  by layer and root by root, without the pad (the 68030 adds it when it
  loads them); `samples.json` says where each starts and loops.
- `instrument.json`: the tables the 68030 player needs: the layer of each
  velocity, each root's volume for each velocity, and for each key its root,
  pan gains and, for each layer, its sample, step, decay factors and attack
  blocks.
- for each piece: `<name>.score` (score.py's stream), `<name>.voices.bin`
  (player3500's voice log) and `<name>.wav` (the 14-bit Paula output,
  held and made band-limited at 44.1 kHz by zoh.py);
- `report.json`.
"""

import json
import statistics
import time
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np

from .. import project
from . import clips, layers, mixer, paula, picture, player3500, samples, score, sfz, zoh
from . import light as light_mod
from . import screen as screen_mod
from .build import Piece

KEY_BYTES_FIXED = 6  # root index and two pan gains
KEY_BYTES_PER_LAYER = 10  # sample index, step (long), release factor, attack blocks
SAMPLE_TABLE_BYTES = 18  # offset, length, loop start, loop length (longs), held factor
WAV_RATE = paula.OUTPUT_RATE


@dataclass(frozen=True)
class Scopes:
    """The player's two scopes: the left output channel's, then the right's."""

    left: tuple[int, int]  # the first column of each scope
    width: int  # columns in each scope


def load_scopes(table: dict) -> Scopes:
    """The recipe's [scopes] table, checked (check_scopes)."""
    try:
        scopes = Scopes(left=tuple(table["left"]), width=table["width"])
    except KeyError as missing:
        raise SystemExit(f"[scopes]: no {missing.args[0]}") from None
    check_scopes(scopes)
    return scopes


def check_scopes(scopes: Scopes) -> None:
    """Two scopes, on byte boundaries, on the screen and apart; SystemExit otherwise.

    The player draws each scope in two halves, and each half must start and
    end on a byte of the row, so the width is a multiple of 16 columns.
    """
    if len(scopes.left) != 2:
        raise SystemExit("[scopes]: give two lefts, the left channel's scope and the right's")
    for left in scopes.left:
        if left % 8:
            raise SystemExit(f"[scopes]: the scope at column {left} does not start on a byte")
    if scopes.width <= 0 or scopes.width % 16:
        raise SystemExit(
            f"[scopes]: a width of {scopes.width} is not a multiple of 16; each half of a"
            " scope must end on a byte"
        )
    for left in scopes.left:
        right = left + scopes.width
        if left < 0 or right > picture.WIDTH:
            raise SystemExit(f"[scopes]: a scope from column {left} to {right} leaves the screen")
    first, second = sorted(scopes.left)
    if second < first + scopes.width:
        raise SystemExit("[scopes]: the two scopes overlap")


@dataclass(frozen=True)
class Recipe:
    sfz: str  # under media/
    out: str  # under the project
    pieces: tuple[Piece, ...]
    spec: samples.SampleSpec
    layers: int  # velocity layers kept
    full_volume: int  # voice volume of the loudest sample at velocity 127
    pan_width: float  # 0 is mono, 1 puts the end keys hard left and right
    budget_bytes: int  # fast RAM for the samples, the tables and the score
    player: str = ""  # the 68030 player's source, under the project
    machine: str = ""  # the amiga.toml machine it runs on
    screen: screen_mod.ScreenSpec | None = None  # the player's screen (from `pieces`'s recipe)
    rotate_s: int = 15  # seconds of quiet before the player plays the next piece by itself
    credits: str = ""  # the full notices, under the project
    scopes: Scopes | None = None  # the player's two scopes, left and right channel
    filter_light: light_mod.FilterLight | None = None  # the filter light (from `pieces`'s recipe)


@dataclass(frozen=True)
class Made:
    """One 16-bit sample: a root in a kept layer."""

    root: int
    layer: int  # index among the kept layers
    region: sfz.Region
    keys: tuple[int, ...]
    data: np.ndarray  # signed 16-bit
    loop_start: int
    rate: float
    level: float  # the recording's peak relative to the loudest sample of the piano
    decay_db_per_s: float
    loop_similarity: float

    @property
    def padded_bytes(self) -> int:
        return 2 * (len(self.data) + mixer.PAD)


@dataclass(frozen=True)
class Piano:
    chosen: list[layers.Layer]
    roots: list[int]
    made: list[Made]
    instrument: player3500.Instrument

    def mix_samples(self) -> list[player3500.MixSample]:
        return [
            player3500.MixSample(mixer.padded(m.data, m.loop_start), len(m.data), m.loop_start)
            for m in self.made
        ]


def load_recipe(path: Path) -> Recipe:
    data = tomllib.loads(path.read_text())
    known = {f.name for f in fields(samples.SampleSpec)}
    unknown = sorted(data.get("samples", {}).keys() - known)
    if unknown:
        raise SystemExit(f"{path} [samples]: unknown key {', '.join(unknown)}")
    shared = _shared(data)
    return Recipe(
        sfz=data["sfz"],
        out=data["out"],
        pieces=_pieces(data, path),
        spec=samples.SampleSpec(**data.get("samples", {})),
        layers=data.get("layers", 8),
        full_volume=data["full_volume"],
        pan_width=data.get("pan_width", 0.5),
        budget_bytes=data["budget_bytes"],
        player=data.get("player", ""),
        machine=data.get("machine", ""),
        screen=screen_mod.load_spec(shared["screen"]) if "screen" in shared else None,
        rotate_s=shared.get("rotate_s", 15),
        credits=data.get("credits", ""),
        scopes=load_scopes(data["scopes"]) if "scopes" in data else None,
        filter_light=light_mod.load(shared["filter_light"]) if "filter_light" in shared else None,
    )


def _shared(data: dict) -> dict:
    """The recipe `pieces` names, whose pieces, screen, rotation and filter light
    this one shares; else this recipe itself."""
    if "pieces" in data:
        return tomllib.loads((project.root() / data["pieces"]).read_text())
    return data


def _pieces(data: dict, path: Path) -> tuple[Piece, ...]:
    data = _shared(data)
    if "piece" not in data:
        raise SystemExit(f"{path}: no [[piece]] tables and no `pieces` recipe")
    return tuple(Piece(p["name"], p["midi"], p.get("title", "")) for p in data["piece"])


def build(recipe_path: Path, clock: Callable[[], float] = time.monotonic) -> dict:
    began = clock()
    recipe = load_recipe(recipe_path)
    media = project.media_dir()
    out = project.root() / recipe.out
    out.mkdir(parents=True, exist_ok=True)

    piano = make_piano(recipe)
    prepared = clock()
    _write_samples(out, piano.made)
    (out / "instrument.json").write_text(json.dumps(instrument_tables(piano), indent=2) + "\n")
    mixing = piano.mix_samples()
    worst = worst_case(piano, mixing)
    errors = interpolation_errors(piano)
    pieces = {}
    for piece in recipe.pieces:
        start = clock()
        perf = score.performance(score.read_midi(media / piece.midi))
        stream = score.encode(perf.events)
        (out / f"{piece.name}.score").write_bytes(stream)
        result = player3500.play(perf.events, piano.instrument, mixing)
        (out / f"{piece.name}.voices.bin").write_bytes(result.log)
        paula.write_wav(out / f"{piece.name}.wav", wav_frames(result))
        pieces[piece.name] = (
            score.report(perf, stream)
            | play_report(result, perf.length_ms, recipe.full_volume)
            | {
                "clips": clips.report(
                    perf.events, result.endings, perf.length_ms, recipe.full_volume * 4 // 64
                ),
                "log_bytes": len(result.log),
                "seconds_to_render": round(clock() - start, 1),
            }
        )

    report = {
        "sfz": recipe.sfz,
        "spec": asdict(recipe.spec),
        "full_volume": recipe.full_volume,
        "pan_width": recipe.pan_width,
        "mix_rate_hz": round(mixer.MIX_RATE, 1),
        "block_samples": mixer.BLOCK,
        "pad_samples": mixer.PAD,
        "layers": layer_rows(piano),
        "samples": [sample_row(m, piano) for m in piano.made],
        "largest_step": round(max_step(piano) / mixer.ONE, 4),
        "memory": memory(piano, pieces, recipe),
        "worst_case": worst,
        "interpolation_error_db": errors,
        "interpolation_error_worst_db": {
            "linear": max(r["linear_db"] for r in errors),
            "nearest": max(r["nearest_db"] for r in errors),
        },
        "largest_sample_difference": max(
            mixer.largest_difference(mixer.padded(m.data, m.loop_start)) for m in piano.made
        ),
        "output_shift": mixer.OUTPUT_SHIFT,
        "peak_sum": max(p["peak_sum"] for p in pieces.values()),
        "peak_dbfs": dbfs(max(p["peak_sum"] for p in pieces.values())),
        "clamped": sum(p["clamped"] for p in pieces.values()),
        "wraps": sum(p["wraps"] for p in pieces.values()),
        "seconds_to_prepare_samples": round(prepared - began, 1),
        "seconds_total": round(clock() - began, 1),
        "pieces": pieces,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def make_piano(recipe: Recipe) -> Piano:
    """The kept layers, the roots and their 16-bit samples, and the player's tables."""
    sfz_path = project.media_dir() / recipe.sfz
    regions = sfz.parse(sfz_path.read_text(), lambda name: (sfz_path.parent / name).read_text())
    notes = samples.note_regions(regions)
    chosen = layers.choose_layers([(r.lovel, r.hivel) for r in notes], recipe.layers)
    by_layer = [samples.layer_regions(regions, layer) for layer in chosen]
    roots = samples.choose_roots(list(by_layer[0]), recipe.spec.spacing)
    if any(set(roots) - set(by_root) for by_root in by_layer):
        raise SystemExit(f"{recipe.sfz}: a kept layer lacks one of the roots {roots}")
    mapping = samples.key_map(roots)
    looped = []
    for index, by_root in enumerate(by_layer):
        for root in roots:
            region = by_root[root]
            rate_in, recording = samples.read_wav(sfz_path.parent / region.sample)
            rate = samples.wanted_rate(root, recipe.spec)
            keys = tuple(k for k, r in mapping.items() if r == root)
            looped.append(
                (
                    index,
                    region,
                    keys,
                    rate,
                    samples.loop_recording(region, recording, rate_in, rate, recipe.spec),
                )
            )
    made = finish(looped, recipe.spec)
    for m in made:
        if mixer.largest_difference(mixer.padded(m.data, m.loop_start)) > 32767:
            raise SystemExit(
                f"root {m.root}, layer {m.layer}: neighbours differ by more than SUB.W holds"
            )
    return Piano(chosen, roots, made, tables(made, chosen, roots, notes, recipe))


def finish(
    looped: list[tuple[int, sfz.Region, tuple[int, ...], float, samples.Looped]],
    spec: samples.SampleSpec,
) -> list[Made]:
    """Normalise each sample to full scale and quantise it to 16 bits; its level keeps
    the recordings' balance (across roots and layers) for the player's volumes."""
    rng = np.random.default_rng(spec.seed)
    peaks = [float(np.max(np.abs(lp.signal))) for *_, lp in looped]
    gained = [
        p * 10 ** (region.volume / 20) for p, (_, region, *_) in zip(peaks, looped, strict=True)
    ]
    loudest = max(gained) or 1.0
    out = []
    for (layer, region, keys, rate, lp), peak, level in zip(looped, peaks, gained, strict=True):
        data = samples.quantise16(lp.signal, spec.peak / (peak or 1.0), rng)
        out.append(
            Made(
                root=region.pitch_keycenter,
                layer=layer,
                region=region,
                keys=keys,
                data=data,
                loop_start=lp.loop_start,
                rate=rate,
                level=level / loudest,
                decay_db_per_s=lp.decay_db_per_s,
                loop_similarity=lp.loop_similarity,
            )
        )
    return out


def tables(
    made: list[Made],
    chosen: list[layers.Layer],
    roots: list[int],
    notes: list[sfz.Region],
    recipe: Recipe,
) -> player3500.Instrument:
    """What each key plays in each layer, and each root's volume for each velocity.

    The release follows the SFZ's ampeg_release for the key (1 s where the
    key has a damper, 5 s where it has none), read as a 60 dB fade, and is
    never slower than the held decay (build.key_sounds's rule).
    """
    if len(made) > player3500.SILENT:
        raise ValueError(f"{len(made)} samples: the voice log numbers them in a byte")
    layer_of = layers.velocity_layers(chosen)
    index = {(m.layer, m.root): i for i, m in enumerate(made)}
    mapping = samples.key_map(roots)
    sounds, pans, root_of = [], [], []
    for key in range(samples.LOWEST_KEY, samples.HIGHEST_KEY + 1):
        root = mapping[key]
        per_layer = []
        for layer, (lovel, _) in enumerate(chosen):
            m = made[index[layer, root]]
            ratio = 2 ** ((key - root) / 12 + m.region.tune / 1200)
            step = mixer.step(m.rate, ratio)
            region = next((r for r in notes if r.plays(key, lovel)), None)
            release_s = region.ampeg_release if region else 1.0
            release_db = max(m.decay_db_per_s, 60 / max(release_s, 0.05))
            per_layer.append(
                player3500.Sound(
                    sample=index[layer, root],
                    step=step,
                    held=player3500.decay_factor(m.decay_db_per_s),
                    release=player3500.decay_factor(release_db),
                    attack_blocks=m.loop_start * mixer.ONE // (step * mixer.BLOCK),
                )
            )
        sounds.append(tuple(per_layer))
        pans.append(mixer.pan_gains(key - samples.LOWEST_KEY, recipe.pan_width))
        root_of.append(roots.index(root))
    volumes = []
    for root in roots:
        mine = [made[index[layer, root]] for layer in range(len(chosen))]
        volumes.append(
            layers.velocity_volumes(
                [m.level for m in mine],
                chosen,
                layer_of,
                [m.region.amp_veltrack for m in mine],
                recipe.full_volume,
            )
        )
    return player3500.Instrument(
        tuple(sounds), tuple(pans), tuple(root_of), tuple(volumes), layer_of
    )


ERROR_ROOTS = (36, 48, 60, 72, 84, 96, 105)  # C2 to A7
ERROR_SECONDS = 0.6


def interpolation_errors(piano: Piano) -> list[dict]:
    """How far the mixer's playback is from an ideal band-limited resample, in dB.

    For each kept layer and each root in ERROR_ROOTS, the root's highest key
    (its largest step) plays the first ERROR_SECONDS of the sample. "linear"
    is the mixer (`mixer.interpolate`); "nearest" is the sample at the
    integer phase, as the mixer did before it interpolated. The ideal is the
    sample upsampled 16 times through its FFT and read at the same positions.
    The error is the energy of the difference over the energy of the ideal.
    """
    rows = []
    for m in piano.made:
        if m.root not in ERROR_ROOTS:
            continue
        key = max(m.keys)
        step = mixer.step(m.rate, 2 ** ((key - m.root) / 12 + m.region.tune / 1200))
        data = mixer.padded(m.data, m.loop_start)
        x = data[: int(m.rate * ERROR_SECONDS)].astype(np.float64)
        positions = step * np.arange(int((len(x) - 4) * mixer.ONE / step), dtype=np.int64)
        ideal = ideal_resample(x, positions)
        rows.append(
            {
                "layer": m.layer,
                "root": m.root,
                "key": key,
                "step": round(step / mixer.ONE, 4),
                "nearest_db": error_db(data[positions >> 16].astype(np.float64), ideal),
                "linear_db": error_db(mixer.interpolate(data, positions).astype(np.float64), ideal),
            }
        )
    return rows


def ideal_resample(x: np.ndarray, positions: np.ndarray, factor: int = 16) -> np.ndarray:
    """x read at 16.16 positions through its FFT, upsampled `factor` times."""
    up = np.fft.irfft(np.fft.rfft(x), len(x) * factor) * factor
    return np.interp(positions / mixer.ONE * factor, np.arange(len(up)), up)


def error_db(y: np.ndarray, ideal: np.ndarray) -> float:
    return round(10 * float(np.log10(((y - ideal) ** 2).sum() / (ideal**2).sum())), 1)


def worst_case(piano: Piano, mixing: list[player3500.MixSample]) -> dict:
    """The loudest sum 16 adjacent keys make, all struck at velocity 127 at once.

    No piece plays this. It shows how far past full scale a performance could
    go at this volume: how many output values it clamps, and whether a 32-bit
    sum wraps.
    """
    worst = {"peak_sum": -1}
    for low in range(len(piano.instrument.sounds) - player3500.VOICES + 1):
        keys = range(low, low + player3500.VOICES)
        events = [score.Event(0, score.NOTE_ON, k, 127) for k in keys]
        events += [score.Event(500, score.NOTE_OFF, k) for k in keys]
        result = player3500.play(events, piano.instrument, mixing)
        if result.peak > worst["peak_sum"]:
            worst = {
                "keys": f"{low + samples.LOWEST_KEY}-{low + samples.LOWEST_KEY + 15}",
                "peak_sum": result.peak,
                "peak_dbfs": dbfs(result.peak),
                "clamped": result.clamped,
                "wraps": result.wraps,
            }
    return worst


def dbfs(peak: int) -> float:
    return round(20 * float(np.log10(max(peak, 1) / 32768)), 1)


def wav_frames(result: player3500.Result) -> np.ndarray:
    """The 14-bit output as Paula plays it, from the two channels a side."""
    left = mixer.paula_output(*mixer.split14(result.left))
    right = mixer.paula_output(*mixer.split14(result.right))
    return zoh.stereo_wav_frames(left, right, WAV_RATE)


def max_step(piano: Piano) -> int:
    return max(s.step for per_key in piano.instrument.sounds for s in per_key)


def layer_rows(piano: Piano) -> list[dict]:
    layer_of = piano.instrument.layer_of
    rows = []
    for index, (low, high) in enumerate(piano.chosen):
        plays = [v for v in range(1, 128) if layer_of[v] == index]
        mine = [m for m in piano.made if m.layer == index]
        rows.append(
            {
                "sfz_velocities": f"{low}-{high}",
                "plays_velocities": f"{plays[0]}-{plays[-1]}",
                "sample_example": mine[0].region.sample,
                "bytes": sum(m.padded_bytes for m in mine),
                "level_median": round(statistics.median(m.level for m in mine), 4),
            }
        )
    return rows


def sample_row(m: Made, piano: Piano) -> dict:
    return {
        "root": m.root,
        "layer": m.layer,
        "keys": f"{m.keys[0]}-{m.keys[-1]}",
        "rate_hz": round(m.rate, 1),
        "samples": len(m.data),
        "bytes_padded": m.padded_bytes,
        "attack_samples": m.loop_start,
        "loop_samples": len(m.data) - m.loop_start,
        "seconds": round(len(m.data) / m.rate, 3),
        "loop_ms": round(1000 * (len(m.data) - m.loop_start) / m.rate, 1),
        "loop_similarity": round(m.loop_similarity, 4),
        "level": round(m.level, 4),
        "decay_db_per_s": round(m.decay_db_per_s, 2),
    }


def memory(piano: Piano, pieces: dict, recipe: Recipe) -> dict:
    sample_bytes = sum(m.padded_bytes for m in piano.made)
    keys = len(piano.instrument.sounds)
    table_bytes = (
        len(piano.instrument.layer_of)
        + len(piano.instrument.volumes) * 128 * 2
        + keys * (KEY_BYTES_FIXED + KEY_BYTES_PER_LAYER * len(piano.chosen))
        + len(piano.made) * SAMPLE_TABLE_BYTES
    )
    score_bytes = max(p["bytes"] for p in pieces.values())
    total = sample_bytes + table_bytes + score_bytes
    return {
        "samples_bytes_padded": sample_bytes,
        "pad_bytes": len(piano.made) * mixer.PAD * 2,
        "per_layer_bytes": [row["bytes"] for row in layer_rows(piano)],
        "tables_bytes": table_bytes,
        "largest_score_bytes": score_bytes,
        "total_bytes": total,
        "budget_bytes": recipe.budget_bytes,
        "headroom_bytes": recipe.budget_bytes - total,
    }


def play_report(result: player3500.Result, length_ms: int, full_volume: int) -> dict:
    minutes = max(length_ms, 1) / 60000
    volumes = [s.volume for s in result.steals]
    return {
        "notes_played": result.notes,
        "restrikes": result.restrikes,
        "notes_superseded_while_waiting": result.superseded,
        "steals": len(result.steals),
        "steals_per_minute": round(len(result.steals) / minutes, 1),
        "steals_of_held_notes": sum(s.held for s in result.steals),
        "stolen_volume_median_of_full": (
            round(statistics.median(volumes) / full_volume, 4) if volumes else None
        ),
        "peak_sum": result.peak,
        "peak_dbfs": dbfs(result.peak),
        "clamped": result.clamped,
        "wraps": result.wraps,
    }


def _write_samples(out: Path, made: list[Made]) -> None:
    offset, index = 0, []
    with (out / "samples.bin").open("wb") as f:
        for m in made:
            f.write(m.data.astype(">i2").tobytes())
            index.append(
                {
                    "offset_bytes": offset,
                    "loop_start": m.loop_start,
                    "samples": len(m.data),
                    "root": m.root,
                    "layer": m.layer,
                }
            )
            offset += 2 * len(m.data)
    (out / "samples.json").write_text(json.dumps(index, indent=2) + "\n")


def instrument_tables(piano: Piano) -> dict:
    ins = piano.instrument
    return {
        "layers": [{"lovel": low, "hivel": high} for low, high in piano.chosen],
        "roots": piano.roots,
        "layer_of_velocity": list(ins.layer_of),
        "volumes": [list(v) for v in ins.volumes],
        "keys": [
            {
                "root": ins.roots[k],
                "pan": list(ins.pans[k]),
                "layers": [asdict(s) for s in ins.sounds[k]],
            }
            for k in range(len(ins.sounds))
        ],
    }
