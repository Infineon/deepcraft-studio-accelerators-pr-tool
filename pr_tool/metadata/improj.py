"""Read DEEPCRAFT Studio ``.improj`` fields used by metadata collection."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from metadata.choices import ALGORITHM, match_choice

# Studio stores PascalCase without spaces; metadata uses the AI Hub spaced labels.
_IMPROJ_PROJECT_TYPE_TO_ALGORITHM: dict[str, str] = {
    'Classification': 'Classification',
    'Regression': 'Regression',
    'ObjectDetection': 'Object Detection',
    'Object Detection': 'Object Detection',
    'ImageClassification': 'Image Classification',
    'Image Classification': 'Image Classification',
}


def _local_tag(tag: str) -> str:
    if isinstance(tag, str) and '}' in tag:
        return tag.rsplit('}', 1)[-1]
    return str(tag)


def read_improj_project_type(improj_path: Path) -> str:
    """Return the ``<ProjectType>`` text from an ``.improj`` file."""
    try:
        root = ET.parse(improj_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f'Could not read {improj_path.name}: {exc}') from exc
    for elem in root.iter():
        if _local_tag(elem.tag) != 'ProjectType':
            continue
        text = (elem.text or '').strip()
        if text:
            return text
    raise ValueError(
        f'No <ProjectType> found in {improj_path.name}. '
        f'Expected one of: Classification, Regression, ObjectDetection, ImageClassification.',
    )


def algorithm_from_project_type(project_type: str) -> str:
    """Map an ``.improj`` ProjectType value to a catalog ``ALGORITHM`` label."""
    raw = project_type.strip()
    if not raw:
        raise ValueError('ProjectType in .improj is empty')
    mapped = _IMPROJ_PROJECT_TYPE_TO_ALGORITHM.get(raw)
    if mapped is not None:
        return mapped
    folded = {key.casefold(): value for key, value in _IMPROJ_PROJECT_TYPE_TO_ALGORITHM.items()}
    mapped = folded.get(raw.casefold())
    if mapped is not None:
        return mapped
    matched = match_choice(raw, ALGORITHM)
    if matched is not None:
        return matched
    expected = ', '.join(('Classification', 'Regression', 'ObjectDetection', 'ImageClassification'))
    raise ValueError(
        f'Unknown ProjectType {raw!r} in .improj. '
        f'Expected one of: {expected}.',
    )


def algorithm_from_improj(project_path: Path, project_name: str) -> str:
    """Derive metadata ``algorithm`` from ``{project_name}.improj``."""
    improj_path = project_path / f'{project_name}.improj'
    if not improj_path.is_file():
        raise ValueError(
            f'Missing {improj_path.name} in {project_path}. '
            f'Accelerator projects need this file so algorithm can be set from <ProjectType>.',
        )
    return algorithm_from_project_type(read_improj_project_type(improj_path))


# Vision Studio project types always use a camera + Vision domain in AI Hub metadata.
VISION_ALGORITHMS = frozenset({'Object Detection', 'Image Classification'})
VISION_SENSORS = ('Camera',)
VISION_DOMAIN = ('Vision',)
VISION_KITS = (
    'PSOC\u2122 Edge AI Kit',
    'PSOC\u2122 Edge Eval Kit',
)
VISION_DEVICES = ('PSOC\u2122 Edge',)


def is_vision_algorithm(algorithm: object) -> bool:
    return isinstance(algorithm, str) and algorithm in VISION_ALGORITHMS


def apply_vision_metadata_defaults(metadata: dict, *, only_missing_kit: bool = False) -> bool:
    """Apply Camera / Vision / Edge kit defaults for vision algorithms.

    When *only_missing_kit* is True, existing kit/device values are left unchanged
    (used when reloading metadata the user may have customized).
    """
    if not is_vision_algorithm(metadata.get('algorithm')):
        return False
    metadata['sensors'] = list(VISION_SENSORS)
    metadata['domain'] = list(VISION_DOMAIN)
    if not only_missing_kit or not (
        isinstance(metadata.get('kit'), list) and metadata['kit']
    ):
        metadata['kit'] = list(VISION_KITS)
    from metadata.choices import devices_for_kits
    kits = metadata.get('kit') if isinstance(metadata.get('kit'), list) else []
    devices = devices_for_kits(kits) if kits else None
    if devices is not None:
        metadata['device'] = devices
    elif not only_missing_kit or not (
        isinstance(metadata.get('device'), list) and metadata['device']
    ):
        metadata['device'] = list(VISION_DEVICES)
    return True


# Backwards-compatible alias used by older call sites.
def apply_vision_sensor_domain(metadata: dict) -> bool:
    return apply_vision_metadata_defaults(metadata, only_missing_kit=False)
