#!/usr/bin/env python3
"""Convert a reservoir box ratio into cups.

The camera stays at one angle, so the box ratio is not cups/14. One table
holds the cup lines from the settled pours at that angle. A reading between
two lines slides in cups. No liquid line is empty.

    python check/volume.py
    python check/volume.py 0.391
"""

import sys
from typing import NamedTuple

FULL_CUPS = 14
OZ_PER_CUP = 5

# (box ratio, cups). Box ratio is how far the water line sits between the
# bottom and the top of the reservoir box. One camera angle. Empty is 0.
# 4, 6, 8, and 10 are the mean of the three settled rounds. 2 is the alarm
# pour. 14 is round 3 only.
LINES: tuple[tuple[float, int], ...] = (
    (0.0, 0),
    (0.22273079838880622, 2),
    (0.3831708317431226, 4),
    (0.5264066757481384, 6),
    (0.6760998404779525, 8),
    (0.7640879285619365, 10),
    (0.9951559305027505, 14),
)


class Reading(NamedTuple):
    box_ratio: float
    cups: float
    percent: float
    fluid_ounces: float


def box_ratio(reservoir_top: float, reservoir_bottom: float, liquid_top: float) -> float:
    """Image y grows downward. The ratio uses the reservoir's top and bottom."""
    height = reservoir_bottom - reservoir_top
    if height <= 0:
        raise ValueError("Reservoir bottom is above its top.")
    return (reservoir_bottom - liquid_top) / height


def _cups(ratio: float) -> float:
    if ratio <= LINES[0][0]:
        return float(LINES[0][1])
    if ratio >= LINES[-1][0]:
        return float(LINES[-1][1])
    for (low_ratio, low_cups), (high_ratio, high_cups) in zip(LINES, LINES[1:]):
        if low_ratio <= ratio <= high_ratio:
            span = high_ratio - low_ratio
            moved = (ratio - low_ratio) / span
            return low_cups + moved * (high_cups - low_cups)
    return float(LINES[-1][1])


def reading(ratio: float | None) -> Reading:
    """None means the frame has a reservoir and no liquid line."""
    if ratio is None:
        ratio = 0.0
    cups = _cups(ratio)
    return Reading(
        ratio,
        cups,
        cups / FULL_CUPS * 100,
        cups * OZ_PER_CUP,
    )


def main(argv: list[str]) -> None:
    if len(argv) == 2:
        got = reading(float(argv[1]))
        print(
            f"box {got.box_ratio:.3f}  "
            f"{got.percent:.1f}%  {got.cups:.2f} cups  {got.fluid_ounces:.1f} fl oz"
        )
        return
    if len(argv) != 1:
        raise SystemExit("usage: python check/volume.py [box-ratio]")
    for ratio, _cups_at_line in LINES:
        got = reading(ratio)
        print(
            f"box {got.box_ratio:.3f}  "
            f"{got.percent:5.1f}%  {got.cups:4.0f} cups  {got.fluid_ounces:5.1f} fl oz"
        )


if __name__ == "__main__":
    main(sys.argv)
