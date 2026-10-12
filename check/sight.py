"""One gauge reading and one person flag from detection boxes."""

from collections.abc import Sequence
from typing import NamedTuple

import volume

# Same 0.4 cutoff the tank and person model calls already use.
THRESHOLD = 0.4

_RESERVOIR = "Reservoir"
_LIQUID = "liquid-level"
_PERSON = "person"


class Box(NamedTuple):
    name: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float


class Seen(NamedTuple):
    gauge_oz: float | None
    person: bool


def chosen(boxes: Sequence[Box]) -> tuple[Box, ...]:
    """The boxes `seen` reads: the best Reservoir, liquid-level, and person."""
    picks = (_best(boxes, _RESERVOIR), _best(boxes, _LIQUID), _best(boxes, _PERSON))
    return tuple(pick for pick in picks if pick is not None)


def seen(boxes: Sequence[Box]) -> Seen:
    reservoir = _best(boxes, _RESERVOIR)
    liquid = _best(boxes, _LIQUID)
    person = _best(boxes, _PERSON) is not None
    if reservoir is None:
        return Seen(None, person)
    if liquid is None:
        ounces = volume.reading(None).fluid_ounces
    else:
        ratio = volume.box_ratio(reservoir.y0, reservoir.y1, liquid.y0)
        ounces = volume.reading(ratio).fluid_ounces
    return Seen(ounces, person)


def _best(boxes: Sequence[Box], name: str) -> Box | None:
    chosen = None
    chosen_score = -1.0
    for box in boxes:
        label = box.name
        if label == "__background__" or label.startswith("background_class"):
            continue
        if label != name or box.score < THRESHOLD:
            continue
        if chosen is None or box.score > chosen_score:
            chosen = box
            chosen_score = box.score
    return chosen
