"""Build a Paula piano from a recipe: samples, scores, voice logs, WAVs, a report.

A recipe (TOML) names an SFZ piano and MIDI performances under media/, the
sample choices (see samples.SampleSpec) and the chip RAM budget. Everything
goes to the recipe's `out` folder under the project.
"""

import csv
import json
import statistics
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .. import project
from . import clips, paula, player, samples, score, sfz

# Bytes the player's tables take in chip or fast RAM, per key and per sample.
KEY_TABLE_BYTES = 8  # sample index, level, period, held and release factors
SAMPLE_TABLE_BYTES = 8  # start address, length and loop start
VELOCITY_TABLE_BYTES = 128 * 2


@dataclass(frozen=True)
class Piece:
    name: str
    midi: str  # under media/


@dataclass(frozen=True)
class Recipe:
    sfz: str  # under media/
    out: str  # under the project
    pieces: tuple[Piece, ...]
    spec: samples.SampleSpec
    budget_bytes: int  # chip RAM for samples, the score, the tables and the program
    program_bytes: int  # an estimate until the 68000 player exists
    velocity_exponent: float
    layer_velocity: int | None  # None: the median velocity of all the pieces


def load_recipe(path: Path) -> Recipe:
    data = tomllib.loads(path.read_text())
    known = {f.name for f in fields(samples.SampleSpec)}
    unknown = sorted(data.get("samples", {}).keys() - known)
    if unknown:
        raise SystemExit(f"{path} [samples]: unknown key {', '.join(unknown)}")
    return Recipe(
        sfz=data["sfz"],
        out=data["out"],
        pieces=tuple(Piece(p["name"], p["midi"]) for p in data["piece"]),
        spec=samples.SampleSpec(**data.get("samples", {})),
        budget_bytes=data["budget_bytes"],
        program_bytes=data["program_bytes"],
        velocity_exponent=data.get("velocity_exponent", 1.5),
        layer_velocity=data.get("layer_velocity"),
    )


def build(recipe_path: Path) -> dict:
    recipe = load_recipe(recipe_path)
    media = project.media_dir()
    out = project.root() / recipe.out
    out.mkdir(parents=True, exist_ok=True)

    performances = {
        p.name: score.performance(score.read_midi(media / p.midi)) for p in recipe.pieces
    }
    every_velocity = [v for perf in performances.values() for v in perf.velocities]
    velocity = recipe.layer_velocity or round(statistics.median(every_velocity))

    sfz_path = media / recipe.sfz
    regions = sfz.parse(sfz_path.read_text(), lambda name: (sfz_path.parent / name).read_text())
    layer = samples.choose_layer(regions, velocity)
    by_root = samples.layer_regions(regions, layer)
    roots = samples.choose_roots(list(by_root), recipe.spec.spacing)
    mapping = samples.key_map(roots)
    prepared = []
    for root in roots:
        region = by_root[root]
        rate, recording = samples.read_wav(sfz_path.parent / region.sample)
        keys = [k for k, r in mapping.items() if r == root]
        prepared.append(samples.prepare(region, recording, rate, keys, recipe.spec))
    made = samples.finish(prepared, recipe.spec)
    sounds = key_sounds(made, mapping, regions, layer)
    table = player.velocity_table(recipe.velocity_exponent)

    _write_samples(out, made)
    pieces = {}
    for piece in recipe.pieces:
        perf = performances[piece.name]
        stream = score.encode(perf.events)
        (out / f"{piece.name}.score").write_bytes(stream)
        result = player.play(perf.events, sounds, table)
        _write_log(out / f"{piece.name}.voices.csv", result.log)
        frames = paula.render(result.writes, made, result.end_ms)
        paula.write_wav(out / f"{piece.name}.wav", frames)
        paula.write_wav(out / f"{piece.name}-a500-filter.wav", paula.a500_filter(frames))
        pieces[piece.name] = (
            score.report(perf, stream)
            | play_report(result, perf.length_ms)
            | {"clips": clips.report(perf.events, result.endings, perf.length_ms)}
        )

    report = {
        "sfz": recipe.sfz,
        "layer": {"velocity": velocity, "lovel": layer[0], "hivel": layer[1]},
        "spec": asdict(recipe.spec),
        "velocity_exponent": recipe.velocity_exponent,
        "samples": [sample_row(s) for s in made],
        "memory": memory(made, pieces, recipe),
        "pieces": pieces,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def key_sounds(
    made: list[samples.PaulaSample],
    mapping: dict[int, int],
    regions: list[sfz.Region],
    layer: tuple[int, int],
) -> list[player.KeySound | None]:
    """What each of the 88 keys plays, decays and releases with.

    The release follows the SFZ's ampeg_release for the key (1 s where the
    key has a damper, 5 s where it has none), read as a 60 dB fade, and is
    never slower than the held decay.
    """
    index = {s.root: i for i, s in enumerate(made)}
    notes = samples.note_regions(regions)
    sounds: list[player.KeySound | None] = []
    for key in range(samples.LOWEST_KEY, samples.HIGHEST_KEY + 1):
        sample = made[index[mapping[key]]]
        region = next((r for r in notes if r.plays(key, layer[0])), None)
        release_s = region.ampeg_release if region else 1.0
        release_db = max(sample.decay_db_per_s, 60 / max(release_s, 0.05))
        sounds.append(
            player.KeySound(
                sample=index[mapping[key]],
                period=sample.periods[key],
                level=round(256 * sample.level),
                held=player.decay_factor(sample.decay_db_per_s),
                release=player.decay_factor(release_db),
                attack_ticks=attack_ticks(sample.loop_start, sample.periods[key]),
            )
        )
    return sounds


def attack_ticks(attack_bytes: int, period: int) -> int:
    """Whole ticks the attack lasts when Paula plays it at period."""
    return attack_bytes * period * player.TICK_HZ // samples.NTSC_CLOCK


def sample_row(s: samples.PaulaSample) -> dict:
    return {
        "root": s.root,
        "keys": f"{s.keys[0]}-{s.keys[-1]}",
        "rate_hz": round(s.rate),
        "period": s.period,
        "bytes": len(s.data),
        "attack_bytes": s.loop_start,
        "loop_bytes": s.loop_length,
        "seconds": round(len(s.data) / s.rate, 3),
        "loop_ms": round(1000 * s.loop_length / s.rate, 1),
        "loop_similarity": round(s.loop_similarity, 4),
        "level": round(s.level, 3),
        "decay_db_per_s": round(s.decay_db_per_s, 2),
        "max_cents_error": round(s.max_cents_error, 2),
    }


def memory(made: list[samples.PaulaSample], pieces: dict, recipe: Recipe) -> dict:
    sample_bytes = sum(len(s.data) for s in made)
    score_bytes = max(p["bytes"] for p in pieces.values())
    tables = 88 * KEY_TABLE_BYTES + len(made) * SAMPLE_TABLE_BYTES + VELOCITY_TABLE_BYTES
    total = sample_bytes + score_bytes + tables + recipe.program_bytes
    return {
        "samples_bytes": sample_bytes,
        "largest_score_bytes": score_bytes,
        "tables_bytes": tables,
        "program_bytes_estimate": recipe.program_bytes,
        "total_bytes": total,
        "budget_bytes": recipe.budget_bytes,
        "headroom_bytes": recipe.budget_bytes - total,
    }


def play_report(result: player.Result, length_ms: int) -> dict:
    minutes = max(length_ms, 1) / 60000
    volumes = [s.volume for s in result.steals]
    return {
        "notes_played": result.notes,
        "restrikes": result.restrikes,
        "notes_dropped_by_player": result.dropped,
        "notes_superseded_while_waiting": result.superseded,
        "steals": len(result.steals),
        "steals_per_minute": round(len(result.steals) / minutes, 1),
        "steals_of_held_notes": sum(s.held for s in result.steals),
        "stolen_volume_median": statistics.median(volumes) if volumes else None,
        "stolen_volume_max": max(volumes, default=None),
        "stolen_volume_histogram": volume_histogram(volumes),
    }


def volume_histogram(volumes: list[int]) -> dict[str, int]:
    """Counts of Paula volumes in bands that double: 1, 2-3, 4-7, 8-15, 16-31, 32-64."""
    bands = {"1": 0, "2-3": 0, "4-7": 0, "8-15": 0, "16-31": 0, "32-64": 0}
    for v in volumes:
        name = list(bands)[min(max(v, 1).bit_length() - 1, 5)]
        bands[name] += 1
    return bands


def _write_samples(out: Path, made: list[samples.PaulaSample]) -> None:
    """All samples end to end, and where each starts and loops: the 68000 player's data."""
    offset, index = 0, []
    with (out / "samples.bin").open("wb") as f:
        for s in made:
            f.write(s.data)
            index.append({"root": s.root, "offset": offset, **sample_row(s)})
            offset += len(s.data)
    (out / "samples.json").write_text(json.dumps(index, indent=2) + "\n")


def _write_log(path: Path, log: list[player.LogRow]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["tick", "ms", "voice", "key", "sample", "period", "volume", "out"])
        for row in log:
            key = row.key + score.LOWEST_NOTE if row.key >= 0 else -1
            writer.writerow(
                [row.tick, row.ms, row.voice, key, row.sample, row.period, row.volume, row.out]
            )
