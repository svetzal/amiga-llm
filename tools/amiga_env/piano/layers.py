"""Velocity layers for the A3500 piano: which layers to keep, and each note's volume.

A layer is an SFZ velocity range, (lovel, hivel). The piano keeps `count`
of the instrument's layers, spread evenly by their centre velocities from
the softest layer to the loudest (`choose_layers`). A velocity plays the
kept layer whose range holds it, else the kept layer whose centre is
nearest (`velocity_layers`).

The volume rule. Each kept sample is normalised to full scale, so a note's
loudness is its voice volume alone. The SFZ gives a note in a layer the
recording's own level times a velocity gain, `1 - t * (1 - (v / 127) ** 2)`
for amp_veltrack t (`sfz_gain`, as sfizz reads it). Here the recording's
level is taken at each kept layer's centre velocity and interpolated in
decibels between centres (held flat beyond the softest and loudest), so
it does not jump where one layer gives way to the next. The note's volume
is `full * level(v) * sfz_gain(v)`: at a layer's centre it is the SFZ's own
loudness, between centres it changes smoothly, and the tone changes at the
layer boundaries. `full` is the volume of the loudest sample at velocity
127.
"""

from collections.abc import Sequence

import numpy as np

Layer = tuple[int, int]
MAX_VOLUME = 32767  # a MULS.W operand is signed


def centre(layer: Layer) -> float:
    return (layer[0] + layer[1]) / 2


def choose_layers(available: Sequence[Layer], count: int) -> list[Layer]:
    """`count` layers whose centres are spread evenly from the softest to the loudest:
    evenly spaced targets, each taking the nearest layer not yet taken."""
    ranges = sorted(set(available), key=centre)
    if count > len(ranges):
        raise ValueError(f"only {len(ranges)} layers to choose {count} from")
    low, high = centre(ranges[0]), centre(ranges[-1])
    chosen: list[Layer] = []
    for i in range(count):
        target = low + (high - low) * i / max(count - 1, 1)
        free = [r for r in ranges if r not in chosen]
        chosen.append(min(free, key=lambda r, t=target: (abs(centre(r) - t), centre(r))))
    return sorted(chosen, key=centre)


def velocity_layers(chosen: Sequence[Layer]) -> tuple[int, ...]:
    """For each MIDI velocity 0 to 127, the index of the kept layer it plays.

    Velocity 0 is not a note; it maps to layer 0 so the table has 128 entries.
    """
    table = [0]
    for velocity in range(1, 128):
        holding = [i for i, (low, high) in enumerate(chosen) if low <= velocity <= high]
        if holding:
            table.append(holding[0])
        else:
            table.append(
                min(range(len(chosen)), key=lambda i: (abs(centre(chosen[i]) - velocity), i))
            )
    return tuple(table)


def sfz_gain(velocity: int, veltrack: float) -> float:
    """The SFZ's velocity gain with the default curve: 1 - t * (1 - (v / 127) ** 2)."""
    t = veltrack / 100
    return 1 - t * (1 - (velocity / 127) ** 2)


def velocity_volumes(
    levels: Sequence[float],
    chosen: Sequence[Layer],
    layer_of: Sequence[int],
    veltracks: Sequence[float],
    full: int,
) -> tuple[int, ...]:
    """One root's voice volume for each velocity 0 to 127 (velocity 0 is 0).

    levels[i] is the root's recorded peak in kept layer i, relative to the
    loudest sample of the piano (1.0); veltracks[i] is that region's
    amp_veltrack.
    """
    centres = [centre(layer) for layer in chosen]
    db = [20 * np.log10(max(level, 1e-9)) for level in levels]
    volumes = [0]
    for velocity in range(1, 128):
        level = 10 ** (float(np.interp(velocity, centres, db)) / 20)
        gain = sfz_gain(velocity, veltracks[layer_of[velocity]])
        volumes.append(min(MAX_VOLUME, max(1, round(full * level * gain))))
    return tuple(volumes)
