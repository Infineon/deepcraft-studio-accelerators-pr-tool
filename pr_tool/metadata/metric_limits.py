"""Plausible ranges for performance metric values, set by the target device.

A value outside its range is almost always a unit mix-up, such as seconds typed
into a millisecond field. Each device caps the figures its memory and clock can
reach. When several devices are listed, the least capable one sets the cap, so
the model can run on every listed device. A device without an entry here, such
as a sensor or a radio, sets no cap. When no listed device has an entry, the
widest cap of all devices applies.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

RW_MEMORY = 'RW Memory Usage (KiB)'
RO_MEMORY = 'RO Memory Usage (KiB)'
SCRATCH_PAD = 'Scratch Pad Size (MB)'
MODEL_WEIGHT = 'Model Weight (MB)'
INFERENCE_TIME = 'Inference Time (ms)'
COMPUTE = 'Compute (MC)'
ENERGY = 'Energy (mJ)'

# The smallest value each figure can take. 1 ns is the floor for an inference.
MINIMUMS: dict[str, float] = {
    RW_MEMORY: 1,
    RO_MEMORY: 1,
    SCRATCH_PAD: 0.001,
    MODEL_WEIGHT: 0.001,
    INFERENCE_TIME: 0.000001,
    COMPUTE: 0.001,
    ENERGY: 0.0000001,
}

# The same for every device: a slow device can legitimately be slow.
_MAX_INFERENCE_TIME_MS = 5000
_MAX_ENERGY_MJ = 5000


def _ceilings(
    rw_kib: float,
    ro_kib: float,
    scratch_mb: float,
    weight_mb: float,
    compute_mc: float,
) -> dict[str, float]:
    return {
        RW_MEMORY: rw_kib,
        RO_MEMORY: ro_kib,
        SCRATCH_PAD: scratch_mb,
        MODEL_WEIGHT: weight_mb,
        INFERENCE_TIME: _MAX_INFERENCE_TIME_MS,
        COMPUTE: compute_mc,
        ENERGY: _MAX_ENERGY_MJ,
    }


# Memory follows on-chip SRAM (RW, scratch pad) and flash (RO, weights). PSOC 6
# and PSOC Edge run models from external flash, so their RO and weight caps use
# 64 MB. Compute is the clock speed times the 5 s time cap, in CPU cycles.
# Keys are the names in ``choices.DEVICE``.
DEVICE_CEILINGS: dict[str, dict[str, float]] = {
    'PSOC\u2122 4': _ceilings(32, 384, 0.03, 0.375, 240),
    'PSOC\u2122 C3': _ceilings(64, 256, 0.06, 0.25, 900),
    'TRAVEO\u2122 T2G body entry': _ceilings(512, 4160, 0.5, 4.06, 800),
    'AURIX\u2122 TC3x': _ceilings(992, 6144, 0.97, 6, 1500),
    'PSOC\u2122 6': _ceilings(1024, 65536, 1, 64, 750),
    'PSOC\u2122 Edge': _ceilings(6656, 65536, 6.5, 64, 2000),
    'AURIX\u2122 TC4x': _ceilings(10832, 20480, 10.58, 20, 2500),
}

# The widest cap for each figure, used when no listed device has an entry.
WIDEST_CEILINGS: dict[str, float] = {
    label: max(row[label] for row in DEVICE_CEILINGS.values())
    for label in MINIMUMS
}


@dataclass(frozen=True)
class MetricRange:
    minimum: float
    maximum: float
    # The device whose cap applies, or ``None`` when no listed device has one.
    limited_by: str | None = None


def metric_range(label: str, devices: Iterable[str] = ()) -> MetricRange | None:
    """Return the allowed range for *label*, or ``None`` when it has no range.

    The cap is the lowest cap among the listed devices that have an entry.
    """
    if label not in MINIMUMS:
        return None
    known = [device for device in dict.fromkeys(devices) if device in DEVICE_CEILINGS]
    if not known:
        return MetricRange(MINIMUMS[label], WIDEST_CEILINGS[label])
    limiting = min(known, key=lambda device: DEVICE_CEILINGS[device][label])
    return MetricRange(MINIMUMS[label], DEVICE_CEILINGS[limiting][label], limiting)


def device_names(value: object) -> list[str]:
    """Read the device names from a saved ``device`` value."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def limit_error(label: str, number: float, devices: Iterable[str] = ()) -> str | None:
    """Return a warning when *number* is outside the range for *label*."""
    allowed = metric_range(label, devices)
    if allowed is None or allowed.minimum <= number <= allowed.maximum:
        return None
    by = f' ({allowed.limited_by} sets the upper limit)' if allowed.limited_by else ''
    return (
        f'{label} must be between {_plain(allowed.minimum)} and '
        f'{_plain(allowed.maximum)}{by}. Please try again.'
    )


def _plain(number: float) -> str:
    """Write *number* without an exponent, such as 0.000001."""
    return f'{number:.10f}'.rstrip('0').rstrip('.')
